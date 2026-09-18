# Database migration ownership

Flyway SQL migrations belong under `db/migration/<module>/V<sequence>__<description>.sql`.

The first business schema migration is intentionally deferred until the data-table design is approved. Migrations must use the owning module's table prefix and must not introduce cross-module foreign keys.
