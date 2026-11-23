#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shellapi.h>
#include <wchar.h>
#include "runtime.h"

typedef int (__cdecl *PythonMain)(int, wchar_t **);

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR command, int show) {
    wchar_t script[32768];
    DWORD length = GetModuleFileNameW(NULL, script, ARRAYSIZE(script));
    if (!length || length >= ARRAYSIZE(script)) return 1;
    wchar_t *filename = wcsrchr(script, L'\\');
    if (!filename || wcscpy_s(filename + 1, ARRAYSIZE(script) - (filename + 1 - script), L"viewer.pyw")) return 1;

    HMODULE runtime = LoadLibraryExW(PYTHON_DLL, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
    PythonMain run = runtime ? (PythonMain)GetProcAddress(runtime, "Py_Main") : NULL;
    if (!run) {
        MessageBoxW(NULL, L"Python could not be loaded. Rebuild the launcher with the installed Python.", L"Mervive Code", MB_ICONERROR);
        return 1;
    }
    int count;
    wchar_t **args = CommandLineToArgvW(GetCommandLineW(), &count);
    if (!args) return 1;
    wchar_t **pythonArgs = LocalAlloc(LPTR, (count + 2) * sizeof(*pythonArgs));
    if (!pythonArgs) { LocalFree(args); return 1; }
    pythonArgs[0] = PYTHON_EXE;
    pythonArgs[1] = script;
    for (int i = 1; i < count; ++i) pythonArgs[i + 1] = args[i];
    int result = run(count + 1, pythonArgs);
    LocalFree(pythonArgs);
    LocalFree(args);
    return result;
}
