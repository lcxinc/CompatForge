#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    unsigned long pid;
    unsigned long address;
    unsigned long length;
    unsigned char *buffer;
    SIZE_T read = 0;
    HANDLE process;
    unsigned long i;

    if (argc != 4) {
        fprintf(stderr, "usage: wow64-read-memory <pid> <address> <length>\n");
        return 2;
    }

    pid = strtoul(argv[1], NULL, 0);
    address = strtoul(argv[2], NULL, 0);
    length = strtoul(argv[3], NULL, 0);
    if (!pid || !address || !length || length > 4096) return 2;

    buffer = malloc(length);
    if (!buffer) return 2;

    process = OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, FALSE, pid);
    if (!process) {
        fprintf(stderr, "OpenProcess failed: %lu\n", GetLastError());
        free(buffer);
        return 1;
    }
    if (!ReadProcessMemory(process, (const void *)(ULONG_PTR)address, buffer, length, &read)) {
        fprintf(stderr, "ReadProcessMemory failed: %lu\n", GetLastError());
        CloseHandle(process);
        free(buffer);
        return 1;
    }

    printf("pid=%lu address=0x%08lx read=%lu\n", pid, address, (unsigned long)read);
    for (i = 0; i < read; i += 16) {
        unsigned long j;
        printf("%08lx:", address + i);
        for (j = 0; j < 16 && i + j < read; ++j) printf(" %02x", buffer[i + j]);
        putchar('\n');
    }

    CloseHandle(process);
    free(buffer);
    return 0;
}
