"""The POC register.

WHY THIS FILE EXISTS
--------------------
A POC that looks finished is dangerous. It renders in the same shell,
with the same tokens, as a page that has been running for months, and
three weeks later nobody remembers which is which.

So every POC is declared here with a stage and, more importantly, with
`blocking`: the list of things that are not true yet. A POC cannot be
promoted by someone deciding it looks fine. It is promoted when the
blocking list is empty, and the page prints that list where the user
can read it.

Stages, deliberately only three:

    wip      being built, numbers may be wrong, do not act on it
    review   complete and honest, waiting for a decision
    klar     blocking list is empty, ready to move out of /poc

Nothing here is automatic. Moving a POC's stage is a human edit to this
file, which is the point: the register is a record of judgements, not a
status computed from whether the code happens to run.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    key: str
    label: str
    pill: str      # jytte.css pill colour
    meaning: str


STAGES: dict[str, Stage] = {
    "wip": Stage("wip", "WIP", "coral",
                 "Under bygning. Tallene kan være forkerte. Handl ikke på dem."),
    "review": Stage("review", "Til review", "gul",
                    "Færdig og ærlig om sine huller. Venter på en beslutning."),
    "klar": Stage("klar", "Klar til PROD", "aqua",
                  "Intet udestående. Kan flyttes ud af /poc."),
}


@dataclass(frozen=True)
class Poc:
    key: str
    title: str
    href: str
    stage: str
    one_liner: str
    # The question the POC exists to answer. If this cannot be written
    # in one sentence, the POC does not have a point yet.
    proves: str
    # What is NOT true yet. Empty list is the only thing that makes a
    # POC promotable, and the page prints it.
    blocking: tuple[str, ...] = ()
    # Where the idea came from, so the design intent survives the author.
    source: str = ""
    started: str = ""

    @property
    def st(self) -> Stage:
        return STAGES.get(self.stage, STAGES["wip"])

    @property
    def promotable(self) -> bool:
        return not self.blocking


POCS: tuple[Poc, ...] = (
    Poc(
        key="poc-systems",
        title="Systemmonitor",
        href="/poc/systems",
        stage="review",
        one_liner="Hvert system som en patient: puls, alder og fejl i træk.",
        proves=("Kan et patientmonitor-layout bruges til at se, hvilke af mine "
                "personlige og forretningsmæssige systemer der har det skidt, "
                "uden at læse en logfil?"),
        blocking=(
            "Azure DevOps står som stabil mens den kaster 401 i loggen. "
            "Dens fetch fanger fejl pr. sektion og returnerer alligevel en "
            "payload med ready: true, så upsert_state nulstiller "
            "fejltælleren. Den halvdel af problemet der kunne løses, er "
            "løst: en payload med ready: false hæver nu til observation og "
            "viser widgettens egen begrundelse, hvilket fandt det "
            "afkortede Projects/_index.json. Men en widget der melder "
            "ready: true med tomme sektioner er stadig usynlig.",
            "Kadencen for n8n-drevne widgets kan Jytte stadig ikke læse, "
            "men den kan nu oplyses: et workflow der sender "
            "expected_minutes (og valgfrit stale_after_minutes) i "
            "payloaden, bliver vurderet som alle andre. vault gør det. "
            "email, calendar og bank gør det ikke endnu og står derfor "
            "som ukendt - det er fire linjer i hvert workflow.",
            "Der er ingen historik. widget_runs er tom, så 'puls' er ét "
            "målepunkt og ikke en kurve. Uden historik kan siden ikke skelne "
            "et udfald fra et mønster.",
            "Ingen alarmering. Siden skal åbnes for at vise noget. En rigtig "
            "monitor siger selv til.",
            "Grupperingen privat/forretning er et gæt i kode, ikke en "
            "beslutning. Den hører til i config, når opdelingen er aftalt.",
        ),
        source=("Layout-idé fra et patient-monitoring dashboard på Dribbble "
                "(shot 27228685). Selve billedet kunne ikke hentes - Dribbble "
                "svarer 202 uden indhold til alt andet end en browser - så "
                "formen er bygget på genrens faste træk og Jyttes egne tokens."),
        started="2026-10-15",
    ),

    Poc(
        key="poc-certifikater",
        title="Certifikater",
        href="/poc/certifikater",
        stage="wip",
        one_liner="Kursusbeviser fra assets/certificates, fundet frem igen.",
        proves=("Kan en mappe med kursusbeviser blive et sted man rent "
                "faktisk finder dem igen, uden at der skal vedligeholdes "
                "metadata ved siden af filerne?"),
        blocking=(
            "Filnavnet er den eneste metadata der findes. Mønsteret "
            "Certificate-<Titel>-<Navn> læses ud af navnet, og filer der "
            "ikke følger det viser bare filnavnet. Det holder til én fil, "
            "ikke til tyve.",
            "Ingen udsteder, intet udstedelsesdato, intet verifikations-"
            "link. Det er netop de tre felter man skal bruge når et bevis "
            "skal fremvises, og ingen af dem kan læses ud af en PNG.",
            "Der er kun én fil at teste på. Gitteret, sorteringen og "
            "PDF-faldbacken er aldrig set med rigtigt indhold.",
            "Beslut om det overhovedet hører til i Jytte. Et kursusbevis "
            "hører måske snarere i vaulten ved siden af CV'et end i et "
            "dashboard.",
        ),
        source=("Egen mappe: C:\\Projects\\jytte\\assets\\certificates. "
                "Første fil er et Technical Leadership Masterclass-bevis, "
                "altså et kursusbevis og ikke et X.509-certifikat - de to "
                "deler ingen felter og skal ikke dele side."),
        started="2026-10-15",
    ),

    Poc(
        key="poc-wow",
        title="WoW Forever",
        href="/poc/wow",
        stage="wip",
        one_liner="Blizzards seneste beta-noter som en gennemgang i spillets eget UI.",
        proves=("Læser en patch note bedre som en tematiseret gennemgang med "
                "ikoner end som Blizzards egen punktliste?"),
        blocking=(
            "Analyzeren kører på en lokal model (Ollama, qwen2.5:7b) på "
            "værten, ikke Claude. Ollama skal køre, ellers beholder siden "
            "den håndtransskriberede note. En 7B-model kan misforstå "
            "indlægget, så hver ny note skal læses mod forumindlægget "
            "før siden stoler på den.",
            "Efter launch 4. november flytter opdateringerne til "
            "hotfix-tråde. Blue tracker-filteret fanger dem, men "
            "JYTTE_WOW_NOTES_TOPIC og JYTTE_WOW_CATEGORIES skal sættes "
            "til de nye id'er, ellers analyseres beta-tråden for evigt.",
            "Ikonvalget for nye Forever-evner (Ruthless, Earth Fury, "
            "Savage, Arcane Wrath, Grim Reach) er et gæt på nærmeste "
            "eksisterende ikon. Skyborne bruger et Blood Elf-portræt.",
        ),
        source=("Artifact bygget i en Claude-session 2026-10-16 fra Blizzards "
                "forumtråd 'WoW Forever Beta Development Notes - updated "
                "October 15'. Flyttet ind i Jytte 2026-10-17."),
        started="2026-10-17",
    ),
)


def by_key(key: str) -> Poc | None:
    return next((p for p in POCS if p.key == key), None)


def summary() -> dict:
    """Counts for the index strip. `promotable` is the number whose
    blocking list has emptied, which is the only number on that page
    worth acting on."""
    counts = {k: 0 for k in STAGES}
    for p in POCS:
        counts[p.stage] = counts.get(p.stage, 0) + 1
    return {
        "total": len(POCS),
        "counts": counts,
        "promotable": sum(1 for p in POCS if p.promotable),
        "blocking_total": sum(len(p.blocking) for p in POCS),
    }
