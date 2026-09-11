### .NET

- **An EF Core migration is three files, not one.** The migration, its sibling
  `.Designer.cs`, and the folder's `*ModelSnapshot.cs`. Generate migrations with
  the EF tooling rather than writing the file by hand — a migration with no
  Designer file is silently SKIPPED by `Database.Migrate()`, so the schema does
  not change and nothing errors.
- **Judge success by exit status**, never by scanning output for the word
  "error". A build that prints warnings and exits 0 succeeded.
