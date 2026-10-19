/* Tests the "Normalisér til dage" Code node in
   deploy/n8n/workflows/elforbrug.json, outside n8n.

     node tests/el_normalize.js

   The JS is pulled out of the committed workflow and run against a
   synthetic Eloverblik CIM payload with n8n's helpers stubbed. The
   point is the shape of the real answer: Eloverblik returns every
   number as a string, nests four levels deep, and indexes days by a
   1-based `position` inside a period rather than by date. Getting the
   off-by-one there wrong shifts an entire month of readings by a day,
   which no eyeball on a bar chart would ever catch.

   Same arrangement as tests/bank_normalize.js. */

const fs = require("fs");
const path = require("path");

const WF = path.join(__dirname, "..", "deploy", "n8n", "workflows",
                     "elforbrug.json");
const doc = JSON.parse(fs.readFileSync(WF, "utf8"));
const node = doc.nodes.find((n) => n.name === "Normalisér til dage");
if (!node) { throw new Error("node 'Normalisér til dage' not in the workflow"); }

let pass = 0, fail = 0;
function check(label, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log("PASS " + label); }
  else { fail++; console.log("FAIL " + label + "\n  got  " + g + "\n  want " + w); }
}

/* --- the n8n helpers the nodes use -------------------------------
   Every node is stubbed with the shape it REALLY outputs, keyed by its
   real name. That distinction is the point: an httpRequest node
   outputs the parsed body, so "Hent maalepunkter" answers
   { result: [...] } and has no .meters, while the Code node after it
   does. This stub used to answer the Code node's shape under the HTTP
   node's name, which is the same slip both Code nodes had made, so the
   tests passed straight over it. */
function nodeOutputs(meters, period, token) {
  return {
    "Config": { ...period },
    "Hent data access token": { result: token },
    "Udpak token": { token, ...period },
    "Hent maalepunkter": { result: meters.map((m) => ({ meteringPointId: m.id })) },
    "Udpak maalepunkter": { token, ...period, meters,
                            ids: meters.map((m) => m.id) },
  };
}

function helpers(outputs) {
  return (name) => {
    if (!(name in outputs)) {
      throw new Error("unexpected $('" + name + "') - not a node in the workflow");
    }
    return { first: () => ({ json: outputs[name] }) };
  };
}

function run(items, meters, period) {
  const $input = { all: () => items };
  const $ = helpers(nodeOutputs(meters, period, "jwt-for-the-test"));
  const fn = new Function("$input", "$", node.parameters.jsCode);
  return fn($input, $)[0].json;
}

// Eloverblik's real wire shape: the reading is under the key
// 'out_Quantity.quantity', dot included. The dot is part of the NAME,
// not a nesting. This fixture used to build a nested
// { out_Quantity: { quantity } } object, so every test below passed
// while production read undefined, fell through to zero and summed
// thirty days of 0,000 kWh. A fixture that is not the wire shape is
// not a test.
function point(pos, q) {
  return { position: String(pos), "out_Quantity.quantity": q,
           "out_Quantity.quality": "A04" };
}

// Kept so the parser stays tolerant of the nested form too: if
// Eloverblik ever stops flattening, that must not break instead.
function nestedPoint(pos, q) {
  return { position: String(pos), out_Quantity: { quantity: q } };
}

function period(start, quantities, mk) {
  return {
    json: {
      result: [{
        MyEnergyData_MarketDocument: {
          TimeSeries: [{
            Period: [{
              timeInterval: { start, end: start },
              Point: quantities.map((q, i) => (mk || point)(i + 1, q)),
            }],
          }],
        },
      }],
    },
  };
}

const METERS = [{ id: "571313000000000000", address: "Testvej 1 2300 København S",
                  type: "E17" }];
const PERIOD = { date_from: "2026-09-16", date_to: "2026-10-15" };

/* --- 1. position is 1-based off the period start, in DANISH days ---
   22:00Z is already the next day in Copenhagen. Taking the UTC date
   labels every reading one day early, and nothing on a bar chart
   would ever reveal it. */
const a = run([period("2026-10-01T22:00:00Z", ["5.5", "7.25", "3"])],
              METERS, PERIOD);
check("22:00Z is the Danish day that has just started",
      a.days[0].date, "2026-10-02");
check("second point is the next day", a.days[1].date, "2026-10-03");
check("third point is the day after", a.days[2].date, "2026-10-04");

/* --- 1b. and it survives the clocks going back -------------------
   The last Sunday in October is 25 hours long. Adding days in
   milliseconds drifts across it; adding them as calendar days does
   not. In 2026 the change is the night of the 25th. */
const dst = run([period("2026-10-23T22:00:00Z",
                        ["1", "1", "1", "1", "1"])], METERS, PERIOD);
check("days stay consecutive across the DST change",
      dst.days.map((d) => d.date),
      ["2026-10-24", "2026-10-25", "2026-10-26", "2026-10-27", "2026-10-28"]);
check("and the winter-time 23:00Z start is read the same way",
      run([period("2026-10-26T23:00:00Z", ["1"])], METERS, PERIOD)
        .days[0].date, "2026-10-27");

/* --- 2. integers, not floats -------------------------------------- */
check("5.5 kWh becomes 5500 thousandths", a.days[0].kwh_x1000, 5500);
check("7.25 kWh becomes 7250", a.days[1].kwh_x1000, 7250);
check("every stored value is an integer",
      a.days.every((d) => Number.isInteger(d.kwh_x1000)), true);

/* --- 3. Danish display -------------------------------------------- */
check("display uses a comma", a.days[0].kwh, "5,500");
check("total is one decimal, comma", a.total_kwh, "15,8");
check("total in thousandths", a.total_kwh_x1000, 15750);

/* --- 4. a comma decimal in the source still parses ----------------- */
const b = run([period("2026-10-01T22:00:00Z", ["5,5"])], METERS, PERIOD);
check("comma decimal from the API parses", b.days[0].kwh_x1000, 5500);

/* --- 5. two metering points on the same day sum ------------------- */
const two = run([period("2026-10-01T22:00:00Z", ["4"]),
                 period("2026-10-01T22:00:00Z", ["6"])], METERS, PERIOD);
check("two meters on one day are summed", two.days[0].kwh_x1000, 10000);
check("and that is still one row", two.days.length, 1);

/* --- 6. bars ------------------------------------------------------- */
check("the biggest day is a full bar", a.days[1].bar, 100);
check("a smaller day is proportional", a.days[0].bar, 76);
const zero = run([period("2026-10-01T22:00:00Z", ["0", "0"])], METERS, PERIOD);
check("an all-zero period does not make NaN bars",
      zero.days.every((d) => Number.isFinite(d.bar)), true);

/* --- 7. empty is not ready ----------------------------------------- */
const none = run([{ json: { result: [] } }], METERS, PERIOD);
check("no readings is not ready", none.ready, false);
check("and says why", none.reason.length > 0, true);
check("readings present means ready", a.ready, true);

/* --- 8. junk does not throw ----------------------------------------- */
const junk = run([{ json: {} }, { json: { result: [{}] } }], METERS, PERIOD);
check("a malformed item is skipped, not fatal", junk.days.length, 0);
const bad = run([period("2026-10-01T22:00:00Z", [null, "2"])], METERS, PERIOD);
check("a null quantity counts as zero", bad.days[0].kwh_x1000, 0);

/* --- 9. the cadence contract ----------------------------------------- */
check("declares its cadence for /poc/systems", a.expected_minutes, 1440);
check("and a staleness window past it", a.stale_after_minutes, 2880);
check("carries the meters through", a.meters.length, 1);
check("carries the period through", a.period.from, "2026-09-16");

/* --- 10. days come out sorted ----------------------------------------- */
const unsorted = run([period("2026-10-05T22:00:00Z", ["1"]),
                      period("2026-10-01T22:00:00Z", ["1"])], METERS, PERIOD);
check("days are sorted ascending",
      unsorted.days.map((d) => d.date), ["2026-10-02", "2026-10-06"]);

/* --- 11. "Udpak maalepunkter": where the 401 came from -------------
   'Hent forbrug' failed with 401 while the two calls before it
   succeeded, which rules out the refresh token: by then the data
   access token had already been used once, on 'Hent maalepunkter'.
   The cause sat one node earlier. 'Udpak maalepunkter' read the token
   off $('Hent data access token'), the raw HTTP node, whose body is
   { result: '<jwt>' } and carries no .token - so it passed undefined
   on and 'Hent forbrug' sent the header "Bearer undefined". */
const unpack = doc.nodes.find((n) => n.name === "Udpak maalepunkter");
if (!unpack) { throw new Error("node 'Udpak maalepunkter' not in the workflow"); }

function runUnpack(outputs) {
  const $json = { result: [{ meteringPointId: "571313000000000000",
                             streetName: "Testvej", buildingNumber: "1",
                             postcode: "2300", cityName: "København S",
                             typeOfMP: "E17" }] };
  const fn = new Function("$json", "$", unpack.parameters.jsCode);
  return fn($json, helpers(outputs))[0].json;
}

const outs = nodeOutputs(METERS, PERIOD, "jwt-for-the-test");
const up = runUnpack(outs);
check("the data access token reaches Hent forbrug",
      up.token, "jwt-for-the-test");
check("and is a string, never undefined", typeof up.token, "string");
check("the metering point ids are passed on",
      up.ids, ["571313000000000000"]);
check("the address is assembled for the page",
      up.meters[0].address, "Testvej 1 2300 København S");

/* A missing token must stop here with a named error, not three nodes
   later as a 401 from Eloverblik. */
let threw = "";
try {
  runUnpack({ ...outs, "Udpak token": { result: "jwt-under-the-wrong-key" } });
} catch (e) { threw = e.message; }
check("a tokenless upstream fails here, by name", threw.length > 0, true);

/* --- 12. no Code node may read from an httpRequest node ------------
   Both defects were one slip: back-referencing the HTTP node instead
   of the Code node that unpacked it. One answered 401; the other
   posted an empty meter list and an undefined period to Jytte without
   complaining. This catches the next one. */
const httpNodes = doc.nodes
  .filter((n) => n.type === "n8n-nodes-base.httpRequest")
  .map((n) => n.name);
const offenders = [];
for (const n of doc.nodes.filter((x) => x.type === "n8n-nodes-base.code")) {
  for (const h of httpNodes) {
    if ((n.parameters.jsCode || "").includes("$('" + h + "')")) {
      offenders.push(n.name + " -> " + h);
    }
  }
}
check("no Code node back-references an httpRequest node", offenders, []);

/* --- 13. the reading is under a key with a dot IN ITS NAME --------
   A green run posted thirty days of 0,000 kWh. Every node succeeded,
   Eloverblik had sent 3.38 kWh for the first day, and the parser read
   p.out_Quantity.quantity - which is undefined, because the key is
   the whole string "out_Quantity.quantity". The old fixture built the
   nested object, so the suite agreed with the bug. */
const flat = run([period("2026-09-17T22:00:00Z", ["3.38"])],
                 METERS, PERIOD);
check("the flat key is read as kWh, not as zero",
      flat.days[0].kwh_x1000, 3380);
check("and it lands on the Danish day", flat.days[0].date, "2026-09-18");
check("so the total is not zero either", flat.total_kwh, "3,4");

const nested = run([period("2026-09-17T22:00:00Z", ["3.38"], nestedPoint)],
                   METERS, PERIOD);
check("the nested form still parses, in case it comes back",
      nested.days[0].kwh_x1000, 3380);

/* A single unreadable point is ordinary; all of them unreadable means
   the shape moved again, and a flat zero line on the page reads as a
   month without electricity. That has to fail loudly. */
let shapeErr = "";
try {
  run([period("2026-09-17T22:00:00Z", ["1", "2"],
              (pos) => ({ position: String(pos), kWh: "9.9" }))],
      METERS, PERIOD);
} catch (e) { shapeErr = e.message; }
check("an unreadable response throws instead of publishing zeroes",
      shapeErr.indexOf("Point-noeglerne") > -1, true);
check("and the error names the keys it did find",
      shapeErr.indexOf("kWh") > -1, true);

/* One missing reading among many is just a gap, not a failure. */
const gap = run([period("2026-09-17T22:00:00Z", ["1.5", "2.5"],
                        (pos, q) => (pos === 1 ? { position: "1" }
                                               : point(pos, q)))],
                METERS, PERIOD);
check("a single gap counts as zero and does not throw",
      gap.days.map((d) => d.kwh_x1000), [0, 2500]);


console.log("\n" + pass + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);
