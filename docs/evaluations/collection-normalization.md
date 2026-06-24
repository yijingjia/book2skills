# Collection Normalization Evaluation

Use this checklist after running collection generation on real book pairs.

## Sample

- Collection:
- Books:
- Date:
- Run/package id:

## Checks

- [ ] `source_kus.json` contains all original source KUs.
- [ ] `same_as_edges.json` records plausible repeated concepts across books as candidate edges.
- [ ] `normalized_ku_groups.json` keeps all member KU ids.
- [ ] `deduped_view.json` is smaller than or equal to source KUs but does not erase source metadata.
- [ ] Similar but contextually different KUs are not blindly collapsed.
- [ ] Generated collection skill remains readable and not noisier than the previous version.

## Notes

Record false merges, missed merges, and useful same_as examples here.
