# ROB RUN AutoClicker

Utilitar Windows pentru jocul **ROB RUN**: cât timp ții apăsat **Ctrl** și **butonul stâng al mouse-ului**, aplicația generează automat click-uri stânga la un interval configurabil. Este util pentru acțiuni repetitive care necesită click stâng, fără să apeși manual de zeci de ori pe secundă.

Aplicația folosește exclusiv API-ul de input al Windows-ului (`WH_MOUSE_LL` + `SendInput`). Nu citește memoria jocului, nu injectează DLL-uri, nu patch-uiește fișiere și nu face niciun acces la rețea.

> **Important:** în modul implicit `intercept`, click-ul fizic de LMB este suprimat cât timp auto-clicker-ul este armat, iar toate click-urile sunt generate de aplicație. Astfel se evită dublarea click-urilor. Dacă jocul nu reacționează la click-uri injectate, încearcă modul `passthrough` sau rulează aplicația ca Administrator.

> **Descărcare:** cele mai recente executabile sunt disponibile în [GitHub Releases](https://github.com/sebastianmeet/robrun-autoclicker/releases/latest). Repository-ul public conține codul sursă; folderele `dist/`, `.venv/` și fișierele de build nu sunt versionate.

---

## Ce face

- **Declanșare:** Ctrl fizic + LMB fizic ținute simultan. Recomandat: apasă întâi **Ctrl**, apoi **LMB**.
- **Click-uri:** cicluri curate `LEFTDOWN` + `LEFTUP`, la `interval_ms` ± `jitter_ms` (implicit 25 ms ± 5 ms, adică aproximativ **40 click-uri/secundă**).
- **Oprire imediată:** la eliberarea Ctrl, a LMB, la pierderea focusului jocului (când `only_in_game=true`) sau la hotkey-ul de ieșire. Worker-ul verifică starea la fiecare ~5 ms, iar butonul sintetic este eliberat mereu la final.
- **Doar în joc:** cu `only_in_game=true`, click-urile sunt emise doar când fereastra din prim-plan aparține procesului configurat în `game_process` (implicit `ROB RUN.exe`).
- **Fără bucle de feedback:** evenimentele injectate de aplicație sunt ignorate de hook (`LLMHF_INJECTED` / `LLMHF_LOWER_IL_INJECTED`), iar fiecare eveniment sintetic are `dwExtraInfo = 0x5255434C`.
- **Siguranță la oprire:** la orice oprire normală, dacă un `LEFTDOWN` sintetic este încă activ, se trimite un `LEFTUP` final. Hook-ul este dezinstalat, iar mutex-ul de instanță unică este eliberat.
- **O singură instanță:** o a doua lansare afișează un mesaj clar și se închide.
- **Fără consolă în release:** `RobRunAutoClicker.exe` rulează silențios. `RobRunAutoClicker-debug.exe` are consolă și afișează tranzițiile de stare.

### Moduri de declanșare

| Mod | Comportament |
|---|---|
| `intercept` (implicit) | Cât timp condiția de armare este îndeplinită, hook-ul **suprimă** evenimentele fizice LMB down/up și numai worker-ul generează click-uri. Este modul recomandat. |
| `passthrough` | Click-ul fizic trece mai departe către joc, iar click-urile sintetice sunt adăugate peste el. Folosit dacă modul intercept nu funcționează în joc. Poate produce un click suplimentar la începutul gestului. |

---

## Fișiere și cerințe

- Windows 10/11 x64.
- **Nu este necesar Python pe calculatorul pe care rulezi `.exe`-ul.**
- Pentru rulare sunt suficiente fișierele din `dist/` (descărcate din GitHub Releases sau generate local):
  - `RobRunAutoClicker.exe` — versiunea release, fără consolă;
  - `RobRunAutoClicker-debug.exe` — versiunea debug, cu consolă;
  - `config.json` — obligatoriu să stea **lângă** executabil;
  - `README.md`.
- Configurația este citită doar la pornire. După editarea `config.json`, repornește aplicația.
- Dacă `config.json` lipsește, este recreat automat cu valorile implicite, în folderul executabilului. Folderul trebuie să fie inscriptibil (evită `C:\Program Files` fără drepturi de administrator).

---

## Configurare

Fișier: `config.json`, în același folder cu `.exe`-ul.

| Cheie | Implicit | Semnificație | Interval / valori valide |
|---|---:|---|---|
| `interval_ms` | `25` | Intervalul țintă între începuturile a două cicluri de click. | Număr întreg, `5`–`500` ms |
| `jitter_ms` | `5` | Variație aleatoare uniformă aplicată fiecărui interval: `±jitter_ms`. | Număr întreg, `0`–`100` ms |
| `only_in_game` | `true` | Dacă este `true`, click-urile sunt emise numai când procesul din prim-plan este cel configurat în `game_process`. | `true` / `false` |
| `exit_hotkey` | `"Ctrl+Alt+F8"` | Combinația globală care oprește aplicația gracefully. | Modificatori: `Ctrl`, `Alt`, `Shift`, `Win`; tastă: `F1`–`F24`, `A`–`Z`, `0`–`9` sau taste uzuale (`Esc`, `Space`, `Tab`, `Insert`, `Delete`, `Home`, `End`, `PageUp`, `PageDown`, săgeți). O singură tastă + modificatori. |
| `trigger_mode` | `"intercept"` | Modul de tratare a click-ului fizic. | `"intercept"` sau `"passthrough"` |
| `game_process` | `"ROB RUN.exe"` | Numele procesului jocului. Comparația se face case-insensitive pe basename. | Text nevid; numele exact din Task Manager → Details |
| `debug_log` | `false` | În build-ul release pornește scrierea în `RobRunAutoClicker.log` lângă `.exe` (dacă nu există consolă). Build-ul debug afișează oricum în consolă. | `true` / `false` |

Exemplu:

```json
{
  "interval_ms": 25,
  "jitter_ms": 5,
  "only_in_game": true,
  "exit_hotkey": "Ctrl+Alt+F8",
  "trigger_mode": "intercept",
  "game_process": "ROB RUN.exe",
  "debug_log": false
}
```

Validare: valorile invalide sau lipsă sunt înlocuite cu valorile implicite, iar aplicația afișează un mesaj clar (consolă în build-ul debug, message box în release). Fișierul invalid nu este suprascris automat. `interval_ms` este intervalul dintre cicluri, nu durata cât stă apăsat butonul; fiecare `LEFTDOWN` este ținut ~3 ms înainte de `LEFTUP`.

> Dacă ROB RUN rulează ca aplicație Roblox, fereastra jocului poate aparține procesului `RobloxPlayerBeta.exe`, nu `ROB RUN.exe`. Verifică numele în Task Manager și setează-l în `game_process`.

---

## Cum rulezi

1. Deschide folderul `dist/`.
2. Verifică `config.json`. Pentru testul în browser setează temporar `"only_in_game": false`.
3. Dublu-click pe `RobRunAutoClicker.exe`.
4. (Opțional, recomandat dacă ROB RUN nu primește click-uri) click dreapta pe executabil → **Run as administrator**. Manifestul de administrator **nu** este inclus intenționat.
5. Deschide ROB RUN, ține **Ctrl**, apoi ține apăsat **butonul stâng** și folosește click-urile generate.
6. Pentru a opri aplicația: **Ctrl+Alt+F8** (sau combinația configurată).

### SmartScreen și antivirus

- La prima rulare, Windows SmartScreen poate afișa „Windows protected your PC”. Apasă **More info → Run anyway**. Acest lucru este normal pentru executabile PyInstaller nesemnate.
- Un antivirus poate semnala un **false positive** pentru auto-clickere/onefile PyInstaller. Nu dezactiva protecția; adaugă excepție doar pentru folderul `dist/` dacă ai încredere în sursă și verifici hash-ul.
- Executabilele nu sunt semnate digital. Pentru distribuție publică ar trebui semnate cu un certificat de code signing.
- Rulează ca Administrator doar dacă este nevoie (UIPI): un proces ne-elevat nu poate injecta input într-un joc/consolă elevată și poate să nu poată citi numele procesului din prim-plan.

### Note de rulare

- Nu porni două instanțe: a doua afișează mesajul „RobRunAutoClicker rulează deja” și se închide.
- Dacă muți `.exe`-ul, mută și `config.json` lângă el.
- Build-ul debug se lansează din consolă:
  ```powershell
  .\dist\RobRunAutoClicker-debug.exe
  ```
  Vei vedea linii precum `[STATE] START`, `[STATE] HOOK installed`, `[STATE] ARMED`, `[STATE] CLICKING`, `[STATE] STOPPED reason=Ctrl released`.
- Build-ul release nu afișează consolă. Cu `"debug_log": true`, scrie `RobRunAutoClicker.log` lângă `.exe`.

---

## Test manual

Deschide `tests/click-counter.html` într-un browser modern (Chrome/Edge/Firefox). Pagina numără evenimentele `mousedown` pentru butonul stâng, afișează totalul și click-urile/secundă pe o fereastră de 2 secunde. **F2** resetează contorul fără a folosi mouse-ul. Fii atent: în modul `only_in_game=true`, atunci când browserul este în prim-plan, click-ul fizic trece prin hook și este numărat; de aceea testul folosește resetarea cu F2 în timp ce ții Ctrl+LMB.

1. **Rată de click-uri**
   - Setează `"only_in_game": false` în `config.json`, salvează și pornește `RobRunAutoClicker.exe`.
   - Focalizează pagina de test.
   - Ține **Ctrl**, apoi **LMB** apăsat peste pagină.
   - **Rezultat așteptat:** contorul crește continuu cu aproximativ **35–45 click-uri/s** (implicit 25 ms ± 5 ms). Click-urile fizice sunt suprimate în modul intercept.
2. **Oprire imediată**
   - Cât timp contorul crește, eliberează doar **Ctrl**; apoi repetă și eliberează doar **LMB**.
   - **Rezultat așteptat:** click-urile se opresc imediat (sub ~50 ms), fără valori care continuă să crească. Nu rămâne niciun buton apăsat.
3. **Doar în joc**
   - Setează `"only_in_game": true`, salvează și repornește aplicația.
   - Focalizează pagina de test (sau altă aplicație), ține Ctrl, apasă LMB (click-ul fizic apare în contor), apoi apasă **F2** cât timp ții Ctrl+LMB apăsat.
   - **Rezultat așteptat:** contorul rămâne la `0`, iar CPS rămâne `0.0`; auto-clicker-ul nu emite click-uri cât timp browserul este în prim-plan. Nu există click-uri repetate.
4. **În ROB RUN**
   - Deschide jocul, alege o zonă/țintă fără risc (nu o acțiune importantă), ține **Ctrl**, apoi **LMB**.
   - **Rezultat așteptat:** click-urile sunt generate rapid cât timp ții ambele taste. Începe cu un interval mai mare dacă vrei să verifici comportamentul jocului.
   - Dacă nu funcționează: vezi secțiunea Troubleshooting (Administrator, borderless, nume proces, passthrough).
5. **Ieșire și stare mouse**
   - Apasă **Ctrl+Alt+F8**.
   - **Rezultat așteptat:** procesul se închide în sub o secundă, hook-ul este dezinstalat, orice `LEFTDOWN` sintetic este urmat de `LEFTUP`, iar click-ul fizic normal funcționează imediat după. Poți relansa aplicația (mutex-ul a fost eliberat).
6. **Config automat**
   - Redenumește temporar `dist/config.json` și pornește exe-ul.
   - **Rezultat așteptat:** `config.json` este recreat cu valorile implicite; aplicația pornește normal. Oprește cu Ctrl+Alt+F8 și restaurează fișierul dacă aveai setări personalizate.
7. **A doua instanță**
   - Cât timp prima instanță rulează, pornește din nou exe-ul.
   - **Rezultat așteptat:** apare mesajul „RobRunAutoClicker rulează deja”; noua instanță se închide, prima rămâne funcțională.

---

## Troubleshooting

### Nu apar click-uri în ROB RUN

- **Rulează ca Administrator.** Un proces normal nu poate trimite input către o fereastră elevată (UIPI). Click dreapta → **Run as administrator**.
- **Încearcă fereastra borderless / windowed**, nu fullscreen exclusiv. Unele jocuri și overlay-uri ignoră sau filtrează inputul injectat în fullscreen exclusiv.
- Verifică `only_in_game`: dacă este `true`, procesul din prim-plan trebuie să fie exact cel din `game_process`. Deschide **Task Manager → Details** și confirmă numele. Pentru Roblox, numele poate fi `RobloxPlayerBeta.exe`; pentru aplicația standalone poate fi `ROB RUN.exe`.
- Confirmă mai întâi că aplicația generează click-uri: setează `only_in_game=false`, pornește build-ul debug și testează pe `tests/click-counter.html`. Dacă acolo merge, problema este în joc (focus/UIPI/fullscreen), nu în worker.
- **Modul intercept vs passthrough:** dacă jocul nu reacționează deloc în `intercept`, setează `"trigger_mode": "passthrough"` și repornește. În passthrough jocul primește click-ul fizic plus click-urile sintetice; este un fallback, nu prima alegere.
- Închide alte auto-clickere, macro-uri sau utilitare care instalează hooks de mouse; pot interfera cu hook-ul nostru.
- Verifică antivirusul: poate bloca `SendInput` sau hook-ul. Folosește versiunea debug pentru mesaje de eroare.

### Verificarea numelui procesului

```powershell
Get-Process | Where-Object { $_.MainWindowTitle -ne "" } |
    Select-Object ProcessName, MainWindowTitle
```

Caută fereastra ROB RUN și notează `ProcessName`. În `config.json`, adaugă extensia `.exe` la nume: de exemplu `"ROB RUN.exe"` sau `"RobloxPlayerBeta.exe"`.

### SmartScreen / antivirus

Vezi secțiunea **Cum rulezi**. Executabilele PyInstaller pot fi raportate ca false positive. Nu dezactiva antivirusul; adaugă o excepție punctuală doar dacă ai verificat sursa. Pentru distribuție, semnează executabilele.

### Conflict pe hotkey

- Implicit este **Ctrl+Alt+F8**. Dacă intră în conflict cu alt program, schimbă `exit_hotkey` într-o combinație validă, de exemplu `"Ctrl+Shift+F10"`.
- Hotkey-ul este global și funcționează indiferent de fereastra activă.
- Nu folosi combinații rezervate de Windows (de exemplu `Ctrl+Alt+Del`).
- Dacă aplicația nu se închide, verifică dacă o altă instanță mai veche rulează (Task Manager).

### Cum verifici că procesul rulează

Deschide **Task Manager → Details** și caută `RobRunAutoClicker.exe` sau `RobRunAutoClicker-debug.exe`. În release nu există fereastră vizibilă; în debug există o consolă. Poți verifica și cu PowerShell:

```powershell
Get-Process RobRunAutoClicker, RobRunAutoClicker-debug -ErrorAction SilentlyContinue
```

### Mouse-ul pare „blocat” după oprire

Aplicația trimite `LEFTUP` final la fiecare oprire normală (inclusiv Ctrl+Alt+F8). Dacă Windows tot raportează butonul apăsat, apasă o dată butonul fizic stâng; este o situație rară, de obicei după terminarea forțată a procesului (Task Manager / crash) exact între `LEFTDOWN` și `LEFTUP`. Nu opri procesul forțat dacă poți folosi hotkey-ul.

### Configurație invalidă

Aplicația folosește valorile implicite pentru câmpurile invalide și afișează un mesaj. În release fără consolă, mesajul apare ca message box. Corectează `config.json` și repornește. Fișierul nu este suprascris automat.

### Limitări cunoscute

- Click-urile sunt trimise la poziția curentă a cursorului. Când `only_in_game=true`, verificarea se bazează pe procesul ferestrei din prim-plan; overlay-urile sau ferestrele care apar peste joc pot schimba ținta.
- Nu funcționează peste ecranul de blocare Windows, prompturi UAC/secure desktop sau în jocuri care filtrează complet inputul injectat.
- Nu poate garanta recunoașterea click-urilor de către joc sau de către sistemele anti-cheat. Verifică manual și respectă regulile jocului.
- O terminare forțată a procesului (kill) poate întrerupe secvența de eliberare a butonului; folosește Ctrl+Alt+F8.

---

## Construirea din sursă

Cerințe: Windows x64, **Python 3.11+** pe PATH, conexiune la internet pentru instalarea PyInstaller. Aplicația nu are dependențe de runtime în afară de biblioteca standard Python.

```powershell
git clone https://github.com/sebastianmeet/robrun-autoclicker.git
cd robrun-autoclicker
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

Scriptul:

1. verifică versiunea Python;
2. creează/reutilizează `.venv`;
3. instalează `requirements-build.txt` (doar PyInstaller);
4. construiește:
   - `dist\RobRunAutoClicker.exe` — `--onefile --noconsole`;
   - `dist\RobRunAutoClicker-debug.exe` — `--onefile --console`;
5. copiază `config.json` și `README.md` în `dist/`;
6. afișează căile absolute ale fișierelor rezultate.

`config.json` **nu** este inclus în executabil: rămâne editabil lângă `.exe`. La rebuild, `build.ps1` suprascrie `dist\config.json` cu cel din rădăcina proiectului, așa că păstrează setările tale în `config.json` din rădăcină dacă vrei să le păstrezi.

Teste unitare pentru validarea configurii:

```powershell
python -m unittest discover -s tests -v
```

Structura sursă:

```text
robrun-autoclicker/            # repository GitHub
├─ main.py                     # hook, worker, config, hotkey, single instance
├─ config.json                 # setări editabile, copiate lângă .exe
├─ build.ps1                   # build release + debug
├─ requirements-build.txt      # PyInstaller (build only)
├─ tests/
│  ├─ test_config.py           # teste unitare pentru config
│  └─ click-counter.html       # contor local de mousedown
└─ dist/                       # generat local de build.ps1, ignorat de Git
```

---

## Disclaimer

Automatizarea inputului poate încălca regulile jocului **ROB RUN**, ale platformei pe care rulează (de exemplu Roblox) sau ale serverelor pe care joci și poate duce la sancțiuni, inclusiv ban. Acest instrument nu este afiliat cu dezvoltatorii sau publisher-ul jocului și este oferit „ca atare”, fără garanții. Îl folosești pe propriul risc și ești singurul responsabil pentru respectarea regulilor aplicabile.
