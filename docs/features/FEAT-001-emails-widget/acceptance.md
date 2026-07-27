# Acceptance - FEAT-001

## Functional

### AC-01 Three buckets render
```gherkin
Given a mailbox with mail from trustworks.dk, dagrofa.dk, and gmail.com
When the emails card renders
Then three columns appear labelled Trustworks, Dagrofa, Private
And each email shows title, topic, urgency badge, description preview
```
**Test location:** `tests/test_emails.py::test_classify_and_shape`

### AC-02 Attachment checkmark
```gherkin
Given an email whose latest message has a Content-Disposition: attachment part
When it renders in a bucket
Then has_attachments is true and a checkmark is shown
And an alternative-only multipart email shows no checkmark
```
**Test location:** `tests/test_emails.py::test_attachment_detection`

### AC-03 Urgency derivation
```gherkin
Given an email with header X-Priority: 1 or subject containing "haster"
Then urgency == "high"
Given a plain email
Then urgency == "normal"
```
**Test location:** `tests/test_emails.py::test_urgency`

### AC-04 Detail drawer
```gherkin
Given a rendered email row
When the user clicks it
Then GET /widgets/emails/detail?uid=&bucket= returns the email drawer
```
**Test location:** manual + route smoke

## Non-functional

### AC-NF-01 Not configured
```gherkin
Given no EMAIL_IMAP_* env vars
When fetch() runs
Then it returns ready:true, configured:false, empty buckets, and never raises
And the card shows a "connect a mailbox" hint
```
**Test location:** `tests/test_emails.py::test_unconfigured`

### AC-NF-02 No secret leak
```gherkin
Given an IMAP auth failure
Then the stored last_error and any log line contain no password value
```
**Test location:** `tests/test_emails.py::test_error_has_no_secret`

## Invariant checklist
- [ ] No secret value in output/logs/templates
- [ ] Timestamps UTC ISO + `data-ts`
- [ ] No AI in fetch path
- [ ] No em/en dash in strings

## Results
- pytest: <paste>
- code-review: <paste>
