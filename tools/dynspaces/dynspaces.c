/* Dynamic spaces for Dokapon Kingdom Connect (Steam): a dinput8.dll proxy that changes board spaces while the game runs.

The game imports only DirectInput8Create from DINPUT8.dll, so this DLL, placed next to DkkStm.exe, is loaded instead of the
system one: it hands that call to the real dinput8.dll and runs a background thread that, every 100 ms:
  - reads the week from the game state (exe global at RVA 0x8A8408 -> state + 0x20; week u16 at +0x1C, weekday u16 at +0x1E),
  - finds the board's 192-byte space records (kind at K, skin at K+2, param at K-4, space index u16 at K-6, x/y/z at K-24),
  - for each "swap A B" line of dynspaces.txt: on even weeks spaces A and B trade kind, skin and param, on odd weeks they are
    put back. A board rebuild (after some battles) resets the records; the next check applies the swap again. A pair waits
    while either space is the current space (exe global RVA 0x8A81C0): a battle reads its space's kind as the terrain and
    crashes if it turns into a non-terrain kind mid-battle.
  - moves the two spaces' discs to match: each disc is a 144-byte quad (6 vertices of xyz, colour, uv) in the game's GPU upload
    buffers (write-combined memory), batched by texture, so trading the two quads' positions trades their looks.
Everything it does is logged to dynspaces.log next to the DLL. See tools/boardview/SpaceTypes.md for how these were found.

build: build.bat (MSVC x64), then copy bin/dinput8.dll and dynspaces.txt into the game folder; delete them to uninstall.
*/
#include <windows.h>
#include <unknwn.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <share.h>

#define RVA_STATE  0x8A8408
#define RVA_CURRENT_SPACE 0x8A81C0
#define REC_STRIDE 192
#define MIN_SPACES 50
#define MAX_PAIRS  32
#define DISC_BYTES 144
#define MAX_COPIES 8

typedef HRESULT(WINAPI *DI8Create)(HINSTANCE, DWORD, REFIID, LPVOID *, LPUNKNOWN);
static DI8Create real_create;
static char folder[MAX_PATH];
static FILE *logfile;

__declspec(dllexport) HRESULT WINAPI DirectInput8Create(HINSTANCE inst, DWORD ver, REFIID riid, LPVOID *out, LPUNKNOWN outer)
{
    if (!real_create) {
        char path[MAX_PATH];
        GetSystemDirectoryA(path, MAX_PATH);
        strcat_s(path, MAX_PATH, "\\dinput8.dll");
        HMODULE m = LoadLibraryA(path);
        real_create = m ? (DI8Create)GetProcAddress(m, "DirectInput8Create") : NULL;
    }
    return real_create ? real_create(inst, ver, riid, out, outer) : E_FAIL;
}

static void logmsg(const char *fmt, ...)
{
    if (!logfile)
        return;
    SYSTEMTIME t;
    GetLocalTime(&t);
    fprintf(logfile, "%02d:%02d:%02d ", t.wHour, t.wMinute, t.wSecond);
    va_list ap;
    va_start(ap, fmt);
    vfprintf(logfile, fmt, ap);
    va_end(ap);
    fputc('\n', logfile);
    fflush(logfile);
}

/* ---- safe memory access: the game frees and reuses memory, so every read of it is guarded ---- */

static int readable(const void *p, size_t n)
{
    MEMORY_BASIC_INFORMATION mbi;
    if (!VirtualQuery(p, &mbi, sizeof mbi) || mbi.State != MEM_COMMIT || (mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS)))
        return 0;
    return (const uint8_t *)p + n <= (const uint8_t *)mbi.BaseAddress + mbi.RegionSize;
}

static int read_u16(const uint8_t *p, uint16_t *v)
{
    __try {
        *v = *(const uint16_t *)p;
        return 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

/* ---- calendar ---- */

static int read_week(int *week, int *weekday)
{
    uint8_t *exe = (uint8_t *)GetModuleHandleA(NULL);
    __try {
        uint8_t *state = *(uint8_t **)(exe + RVA_STATE);
        if (!state || !readable(state, 0x20))
            return 0;
        *week = *(uint16_t *)(state + 0x1C);
        *weekday = *(uint16_t *)(state + 0x1E);
        /* week 1 day 0 is what the block holds before it is filled (after loading a save it stayed so until a battle):
           a game starts on Monday (day 1) of week 1, so it never happens in play */
        return *week > 0 && *week < 1000 && *weekday < 7 && !(*week == 1 && *weekday == 0);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

/* ---- space records ---- */

typedef struct {
    uint32_t param;
    uint8_t kind, skin;
} SpaceData;

static uint8_t *recs; /* address of space 0's kind byte */
static int nspaces;

static int record_index_ok(int i)
{
    uint16_t v;
    return recs && i < nspaces && read_u16(recs + (size_t)i * REC_STRIDE - 6, &v) && v == i;
}

static int records_valid(void)
{
    return record_index_ok(0) && record_index_ok(nspaces / 2) && record_index_ok(nspaces - 1);
}

/* The records are found by their space index (u16 at K-6) counting 0, 1, 2... every 192 bytes. */
static int find_records(void)
{
    uint8_t *a = 0;
    MEMORY_BASIC_INFORMATION mbi;
    while (VirtualQuery(a, &mbi, sizeof mbi)) {
        uint8_t *b = (uint8_t *)mbi.BaseAddress, *end = b + mbi.RegionSize;
        if (mbi.State == MEM_COMMIT && mbi.Type == MEM_PRIVATE && mbi.Protect == PAGE_READWRITE && mbi.RegionSize >= REC_STRIDE * MIN_SPACES) {
            __try {
                for (uint8_t *p = b; p + REC_STRIDE * MIN_SPACES <= end; p += 2) {
                    if (*(uint16_t *)p != 0 || *(uint16_t *)(p + REC_STRIDE) != 1 || *(uint16_t *)(p + 2 * REC_STRIDE) != 2)
                        continue;
                    int n = 3;
                    while (p + (size_t)(n + 1) * REC_STRIDE <= end && *(uint16_t *)(p + (size_t)n * REC_STRIDE) == n)
                        n++;
                    float y = *(float *)(p - 14); /* y at K-20 = index-14 */
                    if (n >= MIN_SPACES && isfinite(y)) {
                        recs = p + 6;
                        nspaces = n;
                        return 1;
                    }
                }
            } __except (EXCEPTION_EXECUTE_HANDLER) {
            }
        }
        a = end;
    }
    return 0;
}

static SpaceData get_space(int i)
{
    uint8_t *k = recs + (size_t)i * REC_STRIDE;
    SpaceData d = {*(uint32_t *)(k - 4), k[0], k[2]};
    return d;
}

static void set_space(int i, SpaceData d)
{
    uint8_t *k = recs + (size_t)i * REC_STRIDE;
    *(uint32_t *)(k - 4) = d.param;
    k[0] = d.kind;
    k[2] = d.skin;
}

static int same(SpaceData x, SpaceData y)
{
    return x.param == y.param && x.kind == y.kind && x.skin == y.skin;
}

/* The space the exe global at RVA 0x8A81C0 points at (24 bytes before its kind), or -1: the current space, where a battle or
   an event may be using the record, so it must not change under it (a battle reads the kind as its terrain). */
static int current_space(void)
{
    uint8_t *exe = (uint8_t *)GetModuleHandleA(NULL);
    uint8_t *cur = *(uint8_t **)(exe + RVA_CURRENT_SPACE) + 24;
    if (cur < recs || cur >= recs + (size_t)nspaces * REC_STRIDE || (cur - recs) % REC_STRIDE)
        return -1;
    return (int)((cur - recs) / REC_STRIDE);
}

static void position(int i, float *x, float *y, float *z)
{
    float *f = (float *)(recs + (size_t)i * REC_STRIDE - 24);
    *x = f[0], *y = f[1], *z = f[2];
}

/* ---- discs ---- */

/* A disc's first vertex is (x + 9, y, z + 9), repeated, then (x - 9, y, z + 9): see SpaceTypes.md. */
static int is_disc(const float *v, float x, float y, float z)
{
    const float *w = (const float *)((const uint8_t *)v + 24), *u = (const float *)((const uint8_t *)v + 48);
    return fabsf(v[0] - (x + 9)) < 0.01f && fabsf(v[2] - (z + 9)) < 0.01f && fabsf(v[1] - y) < 0.01f &&
           w[0] == v[0] && w[2] == v[2] && fabsf(u[0] - (x - 9)) < 0.01f && u[2] == v[2];
}

/* Every disc quad at (x, y, z) in the write-combined (GPU upload) buffers; returns how many (one per buffer copy). */
static int find_discs(float x, float y, float z, uint8_t **out, int max)
{
    int n = 0;
    uint8_t *a = 0;
    MEMORY_BASIC_INFORMATION mbi;
    while (n < max && VirtualQuery(a, &mbi, sizeof mbi)) {
        uint8_t *b = (uint8_t *)mbi.BaseAddress, *end = b + mbi.RegionSize;
        if (mbi.State == MEM_COMMIT && mbi.Protect == (PAGE_READWRITE | PAGE_WRITECOMBINE)) {
            __try {
                float want = x + 9;
                for (uint8_t *p = b; p + DISC_BYTES <= end && n < max; p += 4)
                    if (*(float *)p == want && is_disc((float *)p, x, y, z))
                        out[n++] = p;
            } __except (EXCEPTION_EXECUTE_HANDLER) {
            }
        }
        a = end;
    }
    return n;
}

/* Trade the positions (not the texture coordinates) of two disc quads. */
static void swap_quads(uint8_t *p, uint8_t *q)
{
    for (int v = 0; v < 6; v++) {
        float t[3];
        memcpy(t, p + 24 * v, 12);
        memcpy(p + 24 * v, q + 24 * v, 12);
        memcpy(q + 24 * v, t, 12);
    }
}

/* ---- pairs ---- */

typedef struct {
    int a, b;
    SpaceData da, db;            /* the board file's values, read when the records were found */
    float ax, ay, az, bx, by, bz;
    uint8_t *qa[MAX_COPIES], *qb[MAX_COPIES]; /* disc quads, as found at a's and b's positions */
    int nq, discs_swapped, held;
    ULONGLONG next_scan;                     /* reading the GPU buffers is slow: a failed search waits 2 s */
} Pair;

static Pair pairs[MAX_PAIRS];
static int npairs;

static void load_config(void)
{
    char path[MAX_PATH];
    sprintf_s(path, MAX_PATH, "%s\\dynspaces.txt", folder);
    FILE *f;
    if (fopen_s(&f, path, "r")) {
        logmsg("no %s: nothing to do", path);
        return;
    }
    char line[256];
    while (fgets(line, sizeof line, f) && npairs < MAX_PAIRS) {
        int a, b;
        if (sscanf_s(line, " swap %d %d", &a, &b) == 2) {
            pairs[npairs].a = a, pairs[npairs].b = b;
            npairs++;
            logmsg("pair: spaces %d and %d trade places on even weeks", a, b);
        }
    }
    fclose(f);
}

static void capture_pairs(void)
{
    for (int i = 0; i < npairs; i++) {
        Pair *p = &pairs[i];
        if (p->a >= nspaces || p->b >= nspaces) {
            logmsg("pair %d/%d: board has only %d spaces, skipped", p->a, p->b, nspaces);
            p->a = p->b = -1;
            continue;
        }
        if (p->a < 0)
            continue;
        p->da = get_space(p->a), p->db = get_space(p->b);
        position(p->a, &p->ax, &p->ay, &p->az);
        position(p->b, &p->bx, &p->by, &p->bz);
        p->nq = 0;
        logmsg("space %d: kind %02x skin %02x param %08x at (%.1f, %.1f); space %d: kind %02x skin %02x param %08x at (%.1f, %.1f)",
               p->a, p->da.kind, p->da.skin, p->da.param, p->ax, p->az, p->b, p->db.kind, p->db.skin, p->db.param, p->bx, p->bz);
    }
}

/* The quads found last time still hold the positions they should; otherwise the buffers were rebuilt or moved. */
static int discs_in_place(Pair *p)
{
    if (!p->nq)
        return 0;
    __try {
        for (int c = 0; c < p->nq; c++) {
            float *va = (float *)p->qa[c], *vb = (float *)p->qb[c];
            int ok = p->discs_swapped ? is_disc(va, p->bx, p->by, p->bz) && is_disc(vb, p->ax, p->ay, p->az)
                                      : is_disc(va, p->ax, p->ay, p->az) && is_disc(vb, p->bx, p->by, p->bz);
            if (!ok)
                return 0;
        }
        return 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

static void update_pair(Pair *p, int want_swapped)
{
    if (p->a < 0)
        return;
    SpaceData now = get_space(p->a);
    int swapped = same(now, p->db) && !same(p->da, p->db);
    int cur = current_space();
    if (swapped != want_swapped && (cur == p->a || cur == p->b)) {
        if (!p->held)
            logmsg("spaces %d/%d: space %d is the current space, waiting", p->a, p->b, cur);
        p->held = 1;
        return;
    }
    p->held = 0;
    if (swapped != want_swapped) {
        set_space(p->a, want_swapped ? p->db : p->da);
        set_space(p->b, want_swapped ? p->da : p->db);
        logmsg("spaces %d/%d: %s", p->a, p->b, want_swapped ? "swapped" : "put back");
    }

    if (!discs_in_place(p)) {
        p->nq = 0;
        if (GetTickCount64() < p->next_scan)
            return;
        /* (re)built buffers are assumed to hold the board's own layout */
        int na = find_discs(p->ax, p->ay, p->az, p->qa, MAX_COPIES);
        int nb = find_discs(p->bx, p->by, p->bz, p->qb, MAX_COPIES);
        p->nq = na < nb ? na : nb;
        p->discs_swapped = 0;
        if (p->nq)
            logmsg("spaces %d/%d: found %d disc copies", p->a, p->b, p->nq);
        else
            p->next_scan = GetTickCount64() + 2000;
    }
    if (p->nq && p->discs_swapped != want_swapped) {
        __try {
            for (int c = 0; c < p->nq; c++)
                swap_quads(p->qa[c], p->qb[c]);
            p->discs_swapped = want_swapped;
            logmsg("spaces %d/%d: discs %s", p->a, p->b, want_swapped ? "swapped" : "put back");
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            p->nq = 0;
        }
    }
}

static DWORD WINAPI worker(LPVOID unused)
{
    (void)unused;
    load_config();
    int last_week = -1, ticks = 0;
    for (;;) {
        Sleep(100);
        int week, weekday;
        if (!npairs || !read_week(&week, &weekday))
            continue;
        if (!records_valid()) {
            if (++ticks % 10)
                continue; /* look for the board once a second, not every tick */
            if (!find_records())
                continue;
            logmsg("board: %d space records at %p", nspaces, recs);
            capture_pairs();
        }
        if (week != last_week) {
            logmsg("week %d, day %d", week, weekday);
            last_week = week;
        }
        __try {
            for (int i = 0; i < npairs; i++)
                update_pair(&pairs[i], week % 2 == 0);
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            recs = NULL;
        }
    }
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved)
{
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(inst);
        GetModuleFileNameA(inst, folder, MAX_PATH);
        char *slash = strrchr(folder, '\\');
        if (slash)
            *slash = 0;
        char path[MAX_PATH];
        sprintf_s(path, MAX_PATH, "%s\\dynspaces.log", folder);
        logfile = _fsopen(path, "w", _SH_DENYWR);   /* readable while the game runs */
        logmsg("dynspaces loaded");
        CreateThread(NULL, 0, worker, NULL, 0, NULL);
    }
    return TRUE;
}
