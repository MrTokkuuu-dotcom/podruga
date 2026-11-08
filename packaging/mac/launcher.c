// Запускалка приложения «Подруга»: находит свой Python внутри приложения и запускает start.py.
// Это настоящая программа (не скрипт) — так её может подписать и проверить Apple.
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char *argv[]) {
    char exe[PATH_MAX], real[PATH_MAX];
    uint32_t size = sizeof(exe);
    if (_NSGetExecutablePath(exe, &size) != 0 || !realpath(exe, real)) return 1;
    char *macos = dirname(real);                       // .../Contents/MacOS
    char contents[PATH_MAX], python[PATH_MAX], start[PATH_MAX];
    snprintf(contents, sizeof(contents), "%s/..", macos);
    snprintf(python, sizeof(python), "%s/Resources/python/bin/python3.11", contents);
    snprintf(start, sizeof(start), "%s/Resources/start.py", contents);
    setenv("PODRUGA_BUNDLED", "1", 1);
    setenv("PYTHONUNBUFFERED", "1", 1);
    setenv("PYTHONDONTWRITEBYTECODE", "1", 1);         // не писать .pyc внутрь подписанного приложения
    unsetenv("PYTHONHOME");
    unsetenv("PYTHONPATH");
    char *args[] = {python, "-B", "-I", start, NULL};
    execv(python, args);
    perror("Подруга: не запустился Python");
    return 1;
}
