#include <stdio.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    const int is_wineserver = strstr(argv[0], "wineserver") != NULL;
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        puts(is_wineserver ? "wineserver-compatforge-11.0" : "wine-compatforge-11.0");
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
