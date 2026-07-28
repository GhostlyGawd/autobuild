# DRAFT — FULL COMPLIANCE CHECK NOT COMPLETE

## Writing control

`autobuild writing-check` is an automated controlled-English precheck. It finds
some long sentences and long descriptive paragraphs in configured Markdown
files. It ignores fenced code blocks.

The precheck uses an approximate word counter. It does not verify the complete
ASD-STE100 dictionary, approved meanings, parts of speech, technical terms,
grammar rules, exceptions, safety traces, or technical accuracy.

## Release boundary

The precheck cannot release text as ASD-STE100 compliant. Full release requires
the authorized Issue 9 standard, approved source data, approved terminology, a
complete word ledger, a complete rule ledger, and correction evidence.

An actual trained ASD-STE100 reviewer and a different authorized technical
reviewer must approve the exact source, output, and evidence digest. Automation
cannot replace either reviewer.

The precheck prints this final status:

```text
NOT RELEASED — COMPLIANCE CHECK INCOMPLETE
```

