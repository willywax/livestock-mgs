# Registry integration (removed)
Registry integration removed 2026-11-08. The `registry_sync_outbox` table and `animals.registry_tag_id` column remain in the database as inert legacy data. No application code references them. Do not reintroduce registry calls without a full design review.

See [decision 0007](../decisions/0007-remove-registry-integration.md). The sibling repo `../tags-src` still contains its own copy of the old contract; it is not maintained here.
