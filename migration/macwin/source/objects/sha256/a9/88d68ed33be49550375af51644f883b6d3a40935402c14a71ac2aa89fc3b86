const fs = require("node:fs");
const Database = require(
  "C:/macwin-portable/beekeeper-studio/resources/app.asar/node_modules/better-sqlite3",
);

const databasePath = process.argv[2];
const resultPath = process.argv[3];

if (!databasePath || !resultPath) {
  process.exitCode = 64;
} else {
  const database = new Database(databasePath);
  database.pragma("journal_mode = WAL");
  database.exec(`
    DROP TABLE IF EXISTS compatibility_results;
    CREATE TABLE compatibility_results (
      id INTEGER PRIMARY KEY,
      application TEXT NOT NULL,
      category TEXT NOT NULL,
      score REAL NOT NULL
    );
  `);

  const insert = database.prepare(
    "INSERT INTO compatibility_results(application, category, score) VALUES (?, ?, ?)",
  );
  database.transaction((rows) => {
    for (const row of rows) insert.run(...row);
  })([
    ["Beekeeper Studio", "\u4e2d\u6587\u6570\u636e", 97.5],
    ["MacWin SQL", "\u6570\u636e\u5e93\u5de5\u5177", 96.0],
  ]);

  const rows = database
    .prepare(
      "SELECT application, category, printf('%.1f', score) AS score FROM compatibility_results ORDER BY id",
    )
    .all();
  const sqliteVersion = database.prepare("SELECT sqlite_version() AS version").get().version;
  const integrity = database.pragma("integrity_check", { simple: true });
  database.close();

  fs.writeFileSync(
    resultPath,
    JSON.stringify({ sqliteVersion, integrity, rows }, null, 2) + "\n",
    "utf8",
  );
}
