# FCC development instructions

- Preserve archived versions and original filenames. Do not edit archived packages in place.
- Use v7.3.2 as the current reference until a successor has been validated with real ESPN/Sleeper data.
- v7.3.3 ALLIGATORS_PPR_PREP is rejected: it used simulated data. Keep it only in archive/discarded; never recommend installing or deploying it.
- Do not present simulated statistics, rosters, projections, or league transactions as real data.
- Never commit credentials, ESPN cookies, sync tokens, signing keys, or service-account secrets.
- For new FCC versions produced while working on this repository, preserve an archive entry, update VERSIONS.md and versions.json with the actual status and checksums, and push the authorized changes to this GitHub repository. Do not claim a push succeeded without checking the remote commit.
- State what was tested and what remains unvalidated. An archive upload does not constitute functional validation.
- This repository currently contains historical packages and previews. Inspect package contents before assuming that a ZIP is a complete buildable Android project; several packages are incremental patches.
