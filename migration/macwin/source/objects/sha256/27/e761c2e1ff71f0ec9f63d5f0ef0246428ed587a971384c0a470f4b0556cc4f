#include <windows.h>
#include <stdio.h>
#include <string.h>

static void append_quoted(char *command, size_t capacity, const char *argument)
{
    size_t used = strlen(command);
    if (used + strlen(argument) + 4 >= capacity) return;
    if (used) strcat(command, " ");
    strcat(command, "\"");
    strcat(command, argument);
    strcat(command, "\"");
}

static void dump_memory(HANDLE process, ULONG_PTR address)
{
    unsigned char buffer[128];
    SIZE_T read = 0;
    unsigned int i;

    if (!address || !ReadProcessMemory(process, (const void *)address,
                                       buffer, sizeof(buffer), &read))
        return;

    printf("object_address=%p object_bytes=%lu\n", (void *)address,
           (unsigned long)read);
    for (i = 0; i < read; i += 16) {
        unsigned int j;
        printf("%08lx:", (unsigned long)address + i);
        for (j = 0; j < 16 && i + j < read; ++j)
            printf(" %02x", buffer[i + j]);
        putchar('\n');
    }

    if (read >= 8) {
        ULONG_PTR message = *(const DWORD *)(buffer + 4);
        DWORD length = 0;
        WCHAR text[513];
        SIZE_T text_read = 0;

        if (message && ReadProcessMemory(process,
                                         (const void *)(message - sizeof(length)),
                                         &length, sizeof(length), &text_read) &&
            text_read == sizeof(length)) {
            if (length > 512) length = 512;
            ZeroMemory(text, sizeof(text));
            if (ReadProcessMemory(process, (const void *)message, text,
                                  length * sizeof(WCHAR), &text_read)) {
                char utf8[2048];
                int converted = WideCharToMultiByte(CP_UTF8, 0, text,
                                                     text_read / sizeof(WCHAR),
                                                     utf8, sizeof(utf8) - 1,
                                                     NULL, NULL);
                if (converted > 0) {
                    utf8[converted] = '\0';
                    printf("exception_message=%s\n", utf8);
                }
            }
        }
    }
}

static void dump_raw(HANDLE process, const char *name, ULONG_PTR address,
                     SIZE_T length)
{
    unsigned char buffer[256];
    SIZE_T read = 0;
    unsigned int i;

    if (length > sizeof(buffer)) length = sizeof(buffer);
    if (!address || !ReadProcessMemory(process, (const void *)address,
                                       buffer, length, &read))
        return;

    printf("%s_address=%p bytes=%lu\n", name, (void *)address,
           (unsigned long)read);
    for (i = 0; i < read; i += 16) {
        unsigned int j;
        printf("%08lx:", (unsigned long)address + i);
        for (j = 0; j < 16 && i + j < read; ++j)
            printf(" %02x", buffer[i + j]);
        putchar('\n');
    }
}

static ULONG_PTR dump_region(HANDLE process, ULONG_PTR address)
{
    MEMORY_BASIC_INFORMATION info;
    SIZE_T size;

    ZeroMemory(&info, sizeof(info));
    size = VirtualQueryEx(process, (const void *)address, &info, sizeof(info));
    if (!size) return 0;

    printf("region_address=%p base=%p allocation_base=%p size=%lu "
           "state=%08lx protect=%08lx type=%08lx\n",
           (void *)address, info.BaseAddress, info.AllocationBase,
           (unsigned long)info.RegionSize, info.State, info.Protect, info.Type);
    return (ULONG_PTR)info.AllocationBase;
}

static BOOL dump_context(DWORD thread_id, CONTEXT *result)
{
    HANDLE thread = OpenThread(THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION,
                               FALSE, thread_id);
    CONTEXT context;

    if (!thread) return FALSE;
    ZeroMemory(&context, sizeof(context));
    context.ContextFlags = CONTEXT_FULL | CONTEXT_FLOATING_POINT |
                           CONTEXT_EXTENDED_REGISTERS;
    if (GetThreadContext(thread, &context)) {
        printf("context eip=%08lx esp=%08lx ebp=%08lx eax=%08lx ebx=%08lx "
               "ecx=%08lx edx=%08lx esi=%08lx edi=%08lx cs=%04lx ss=%04lx "
               "eflags=%08lx\n",
               context.Eip, context.Esp, context.Ebp, context.Eax,
               context.Ebx, context.Ecx, context.Edx, context.Esi,
               context.Edi, context.SegCs, context.SegSs, context.EFlags);
        printf("x87 control=%08lx status=%08lx tag=%08lx error_offset=%08lx "
               "error_selector=%08lx data_offset=%08lx data_selector=%08lx\n",
               context.FloatSave.ControlWord, context.FloatSave.StatusWord,
               context.FloatSave.TagWord, context.FloatSave.ErrorOffset,
               context.FloatSave.ErrorSelector, context.FloatSave.DataOffset,
               context.FloatSave.DataSelector);
        if (result) *result = context;
        CloseHandle(thread);
        return TRUE;
    }
    CloseHandle(thread);
    return FALSE;
}

int main(int argc, char **argv)
{
    STARTUPINFOA startup;
    PROCESS_INFORMATION process;
    DEBUG_EVENT event;
    char command[4096] = "";
    DWORD continue_status;
    unsigned int exception_count = 0;
    ULONG_PTR wow64cpu_base = 0;
    int i;

    if (argc < 2) {
        fprintf(stderr, "usage: wow64-debug-exception <exe> [args...]\n");
        return 2;
    }
    for (i = 1; i < argc; ++i) append_quoted(command, sizeof(command), argv[i]);

    ZeroMemory(&startup, sizeof(startup));
    startup.cb = sizeof(startup);
    ZeroMemory(&process, sizeof(process));
    if (!CreateProcessA(NULL, command, NULL, NULL, FALSE,
                        DEBUG_ONLY_THIS_PROCESS, NULL, NULL, &startup, &process)) {
        fprintf(stderr, "CreateProcess failed: %lu\n", GetLastError());
        return 1;
    }
    printf("debuggee_pid=%lu command=%s\n", process.dwProcessId, command);

    for (;;) {
        if (!WaitForDebugEvent(&event, 15000)) {
            fprintf(stderr, "WaitForDebugEvent failed: %lu\n", GetLastError());
            TerminateProcess(process.hProcess, 124);
            break;
        }

        continue_status = DBG_CONTINUE;
        switch (event.dwDebugEventCode) {
        case EXCEPTION_DEBUG_EVENT: {
            const EXCEPTION_DEBUG_INFO *exception = &event.u.Exception;
            const EXCEPTION_RECORD *record = &exception->ExceptionRecord;
            CONTEXT context;
            DWORD index;

            printf("exception code=%08lx first_chance=%lu address=%p params=%lu\n",
                   record->ExceptionCode, exception->dwFirstChance,
                   record->ExceptionAddress, record->NumberParameters);
            for (index = 0; index < record->NumberParameters; ++index)
                printf("info[%lu]=%p\n", index,
                       (void *)record->ExceptionInformation[index]);
            if (dump_context(event.dwThreadId, &context) &&
                record->ExceptionCode == EXCEPTION_ACCESS_VIOLATION) {
                ULONG_PTR allocation_base = dump_region(process.hProcess, context.Eip);
                dump_raw(process.hProcess, "code", context.Eip > 64 ? context.Eip - 64 : 0, 160);
                if (allocation_base)
                    dump_raw(process.hProcess, "image_transition_buffer",
                             allocation_base + 0x8000, 64);
                if (wow64cpu_base)
                    dump_raw(process.hProcess, "wow64cpu_transition",
                             wow64cpu_base + 0x7000, 64);
                dump_raw(process.hProcess, "stack", context.Esp, 256);
                dump_raw(process.hProcess, "frame", context.Ebp - 64, 160);
            }
            if (record->ExceptionCode == 0x0eedfade &&
                record->NumberParameters > 1)
                dump_memory(process.hProcess, record->ExceptionInformation[1]);

            ++exception_count;
            if (record->ExceptionCode != EXCEPTION_BREAKPOINT)
                continue_status = DBG_EXCEPTION_NOT_HANDLED;
            break;
        }
        case EXIT_PROCESS_DEBUG_EVENT:
            printf("process_exit=%lu exceptions=%u\n",
                   event.u.ExitProcess.dwExitCode, exception_count);
            ContinueDebugEvent(event.dwProcessId, event.dwThreadId,
                               DBG_CONTINUE);
            CloseHandle(process.hThread);
            CloseHandle(process.hProcess);
            return 0;
        case CREATE_PROCESS_DEBUG_EVENT:
            if (event.u.CreateProcessInfo.hFile)
                CloseHandle(event.u.CreateProcessInfo.hFile);
            break;
        case LOAD_DLL_DEBUG_EVENT:
            if (event.u.LoadDll.hFile) {
                char path[MAX_PATH * 4];
                DWORD length = GetFinalPathNameByHandleA(event.u.LoadDll.hFile,
                                                         path, sizeof(path), 0);
                if (length && length < sizeof(path)) {
                    printf("load_dll base=%p path=%s\n",
                           event.u.LoadDll.lpBaseOfDll, path);
                    if (strstr(path, "wow64cpu.dll"))
                        wow64cpu_base = (ULONG_PTR)event.u.LoadDll.lpBaseOfDll;
                }
                CloseHandle(event.u.LoadDll.hFile);
            }
            break;
        }

        if (!ContinueDebugEvent(event.dwProcessId, event.dwThreadId,
                                continue_status)) {
            fprintf(stderr, "ContinueDebugEvent failed: %lu\n", GetLastError());
            break;
        }
    }

    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return 1;
}
