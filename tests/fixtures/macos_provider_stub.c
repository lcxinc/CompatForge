#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

int main(int argc, char **argv) {
    const int is_wineserver = strstr(argv[0], "wineserver") != NULL;
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        puts(is_wineserver ? "wineserver-compatforge-11.0" : "wine-compatforge-11.0");
        return 0;
    }
    if (!is_wineserver && argc >= 2 && strcmp(argv[1], "wineboot") == 0) {
        const char *prefix = getenv("WINEPREFIX");
        if (prefix == NULL) {
            return 2;
        }
        char drive_c[4096];
        char windows[4096];
        char system32[4096];
        char marker[4096];
        if (snprintf(drive_c, sizeof(drive_c), "%s/drive_c", prefix) < 0
            || snprintf(windows, sizeof(windows), "%s/windows", drive_c) < 0
            || snprintf(system32, sizeof(system32), "%s/system32", windows) < 0
            || snprintf(marker, sizeof(marker), "%s/ntdll.dll", system32) < 0) {
            return 2;
        }
        (void)mkdir(drive_c, 0700);
        (void)mkdir(windows, 0700);
        (void)mkdir(system32, 0700);
        FILE *file = fopen(marker, "wb");
        if (file == NULL) {
            return 2;
        }
        fputs("compatforge-prefix", file);
        fclose(file);
        return 0;
    }
    if (is_wineserver) {
        return 0;
    }
    puts("COMPATFORGE_MACOS_PROVIDER_LAUNCH_OK");
    fflush(stdout);
    sleep(30);
    return 0;
}
