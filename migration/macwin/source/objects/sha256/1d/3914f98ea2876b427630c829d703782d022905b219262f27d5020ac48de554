#include <stdio.h>
#include <windows.h>

typedef struct sqlite3 sqlite3;
typedef int (*sqlite3_open_fn)(const char *, sqlite3 **);
typedef int (*sqlite3_close_fn)(sqlite3 *);
typedef int (*sqlite3_exec_fn)(sqlite3 *, const char *, int (*)(void *, int, char **, char **), void *, char **);
typedef const char *(*sqlite3_errmsg_fn)(sqlite3 *);
typedef void (*sqlite3_free_fn)(void *);

static int row_callback(void *unused, int count, char **values, char **columns)
{
    int index;
    (void)unused;
    (void)columns;
    fputs("MACWIN_SQLITE_ROW=", stdout);
    for (index = 0; index < count; ++index) {
        if (index != 0)
            fputc('|', stdout);
        fputs(values[index] ? values[index] : "NULL", stdout);
    }
    fputc('\n', stdout);
    return 0;
}

static int integrity_callback(void *unused, int count, char **values, char **columns)
{
    (void)unused;
    (void)columns;
    if (count == 1 && values[0])
        printf("MACWIN_SQLITE_INTEGRITY=%s\n", values[0]);
    return 0;
}

int main(int argc, char **argv)
{
    HMODULE module;
    sqlite3 *database = NULL;
    sqlite3_open_fn sqlite3_open_ptr;
    sqlite3_close_fn sqlite3_close_ptr;
    sqlite3_exec_fn sqlite3_exec_ptr;
    sqlite3_errmsg_fn sqlite3_errmsg_ptr;
    sqlite3_free_fn sqlite3_free_ptr;
    char loaded_path[MAX_PATH];
    char *error = NULL;
    int result;
    const char *setup_sql =
        "PRAGMA journal_mode=WAL;"
        "DROP TABLE IF EXISTS applications;"
        "CREATE TABLE applications("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, score REAL NOT NULL);"
        "INSERT INTO applications(name, category, score) VALUES"
        "('DB Browser', '\xE4\xB8\xAD\xE6\x96\x87\xE6\x95\xB0\xE6\x8D\xAE', 98.5),"
        "('MacWin CAD', '\xE5\xB7\xA5\xE7\xA8\x8B\xE8\xBD\xAF\xE4\xBB\xB6', 96.0);";
    const char *query_sql =
        "SELECT name, category, printf('%.1f', score) FROM applications ORDER BY id;";

    if (argc != 2) {
        fprintf(stderr, "usage: sqlitebrowser-probe.exe DATABASE\n");
        return 64;
    }

    module = LoadLibraryA("sqlite3.dll");
    if (!module) {
        fprintf(stderr, "LoadLibrary(sqlite3.dll) failed: %lu\n", GetLastError());
        return 65;
    }
    if (GetModuleFileNameA(module, loaded_path, sizeof(loaded_path)) == 0) {
        fprintf(stderr, "GetModuleFileName(sqlite3.dll) failed: %lu\n", GetLastError());
        return 66;
    }
    printf("MACWIN_SQLITE_DLL=%s\n", loaded_path);

#define LOAD_SQLITE_SYMBOL(name) \
    union { FARPROC proc; name##_fn fn; } name##_symbol; \
    name##_symbol.proc = GetProcAddress(module, #name); \
    name##_ptr = name##_symbol.fn; \
    if (!name##_ptr) { \
        fprintf(stderr, "GetProcAddress(%s) failed\n", #name); \
        return 67; \
    }
    LOAD_SQLITE_SYMBOL(sqlite3_open)
    LOAD_SQLITE_SYMBOL(sqlite3_close)
    LOAD_SQLITE_SYMBOL(sqlite3_exec)
    LOAD_SQLITE_SYMBOL(sqlite3_errmsg)
    LOAD_SQLITE_SYMBOL(sqlite3_free)
#undef LOAD_SQLITE_SYMBOL

    result = sqlite3_open_ptr(argv[1], &database);
    if (result != 0) {
        fprintf(stderr, "sqlite3_open failed: %s\n", database ? sqlite3_errmsg_ptr(database) : "unknown");
        if (database)
            sqlite3_close_ptr(database);
        return 68;
    }

    result = sqlite3_exec_ptr(database, setup_sql, NULL, NULL, &error);
    if (result != 0) {
        fprintf(stderr, "setup SQL failed: %s\n", error ? error : sqlite3_errmsg_ptr(database));
        if (error)
            sqlite3_free_ptr(error);
        sqlite3_close_ptr(database);
        return 69;
    }
    result = sqlite3_exec_ptr(database, query_sql, row_callback, NULL, &error);
    if (result == 0)
        result = sqlite3_exec_ptr(database, "PRAGMA integrity_check;", integrity_callback, NULL, &error);
    if (result != 0) {
        fprintf(stderr, "query SQL failed: %s\n", error ? error : sqlite3_errmsg_ptr(database));
        if (error)
            sqlite3_free_ptr(error);
        sqlite3_close_ptr(database);
        return 70;
    }

    result = sqlite3_close_ptr(database);
    FreeLibrary(module);
    if (result != 0) {
        fprintf(stderr, "sqlite3_close failed: %d\n", result);
        return 71;
    }
    return 0;
}
