# Golden envelopes

Each file here is one real message, exactly as it travels between services. A sending service
writes this; a receiving service must be able to read it.

Changing an existing file is a **breaking change**: bump the event to a new version and add a new
golden file instead. Adding a field to a payload is safe and needs no new file — readers ignore
fields they do not recognise.
