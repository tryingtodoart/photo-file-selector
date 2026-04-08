# Photo File Selector — Manual de utilizare

**Plugin pentru Lightroom Classic**
Versiunea 1.0 · [github.com/tryingtodoart/photo-file-selector](https://github.com/tryingtodoart/photo-file-selector)

---

## Ce face acest plugin

După ce livrezi unui client o galerie cu imagini cu watermark, clientul îți trimite selecția lui — un folder cu pozele alese, un mesaj WhatsApp cu numere, un fișier .txt sau o foaie Excel. Tu trebuie apoi să găsești manual fișierele RAW corespunzătoare în catalogul Lightroom și să le marchezi.

Acest plugin automatizează procesul: îi spui ce a ales clientul, el caută în catalog și aplică automat o stea și/sau o etichetă de culoare pe pozele potrivite.

---

## 1. Instalare

### 1.1 Descarcă plugin-ul

Descarcă folderul `photo-selector-lr.lrplugin` de pe pagina de [Releases](https://github.com/tryingtodoart/photo-file-selector/releases) a proiectului și salvează-l într-un loc fix pe calculator (de exemplu `Documente\LightroomPlugins\`). Nu muta folderul după instalare.

### 1.2 Adaugă plugin-ul în Lightroom Classic

1. Deschide **Lightroom Classic**.
2. Din meniu, mergi la **File → Plug-in Manager…** (sau apasă `Ctrl+Alt+Shift+,`).
3. În fereastra care se deschide, apasă butonul **Add** din stânga jos.
4. Navighează la folderul `photo-selector-lr.lrplugin` și apasă **Select Folder** (pe Windows) sau **Choose** (pe Mac).
5. Plugin-ul apare în listă cu statusul **Installed and running**.
6. Apasă **Done**.

> Plugin-ul trebuie reinstalat dacă muți folderul după instalare. Dacă se întâmplă asta, repetă pașii de mai sus.

---

## 2. Deschiderea plugin-ului

Plugin-ul se accesează din modulul **Library**:

**Library → Plugin Extras → Photo File Selector…**

Se deschide o fereastră de dialog cu toate opțiunile.

---

## 3. Fereastra de dialog — secțiuni

### 3.1 Client Selection — Selecția clientului

Această secțiune îi spune plugin-ului *ce* a ales clientul. Există trei modalități de a introduce selecția — le poți folosi simultan, rezultatele se combină.

---

#### Folder selection

Apasă **Folder selection** dacă clientul ți-a trimis un folder cu imaginile alese (de obicei JPEG-uri cu watermark sau copii reduse).

- Se deschide un browser de foldere.
- Selectează folderul primit de la client.
- Calea apare în câmpul de text de mai jos.

Plugin-ul citește numele fișierelor din acel folder și extrage numerele de identificare (de exemplu din `C86A0155.jpg` extrage `0155`).

---

#### File selection

Apasă **File selection** dacă clientul ți-a trimis o listă de numere într-un fișier `.txt` sau `.csv`.

- Se deschide un browser de fișiere.
- Selectează fișierul primit.
- Calea apare în câmpul de text de mai jos.

> **Notă despre Excel:** Dacă clientul a trimis un fișier `.xls` sau `.xlsx`, deschide-l și salvează-l ca `.csv` (File → Save As → CSV), apoi folosește **File selection**.

---

#### Câmpul de cale

Câmpul de text de sub butoane arată calea selectată. Poți și să scrii sau să lipești o cale direct în el, fără să folosești butoanele.

---

#### Lipire text (paste)

Dacă clientul ți-a trimis selecția printr-un mesaj — WhatsApp, SMS, e-mail, etc. — copiază mesajul și lipește-l direct în căsuța de text mare.

**Exemple de formate acceptate:**

```
Te rog trimite-mi pozele 155, 175 și 320.
```
```
155
175
245
275
320
603
```
```
Aș vrea 0042, 0087 și 0210.
```

Plugin-ul înțelege numerele indiferent de contextul din jur — virgule, spații, cuvinte, nu contează.

Butonul **Clear** șterge conținutul căsuței de text.

---

### 3.2 Filename Settings — Setări de denumire

Aceste setări îi explică plugin-ului cum sunt denumite fișierele tale, pentru a ști cum să extragă numărul de identificare din nume.

#### Prefix

Prefixul este partea fixă din numele fișierului, înainte de numărul secvențial.

| Exemplu de fișier | Prefix |
|---|---|
| `C86A0042.CR2` | `C86A` |
| `IMG_0042.CR2` | `IMG_` |
| `DSC_0042.NEF` | `DSC_` |

- Dacă lași câmpul gol, plugin-ul încearcă să detecteze automat numărul.
- Prefixul este salvat automat între sesiuni — nu trebuie să-l introduci de fiecare dată.

#### Sequence digits — Număr de cifre

Câte cifre are numărul secvențial din numele fișierului. Implicit este **4** (adică `0042`).

Dacă fișierele tale au numere de 4 cifre (`0042`) și clientul trimite `42`, plugin-ul completează automat zerouri la stânga → `0042`.

---

### 3.3 Search Scope — Domeniu de căutare

Determină *unde* caută plugin-ul în catalogul tău Lightroom.

#### Currently selected folder / collection *(implicit)*

Caută doar în folderul sau colecția selectată în panoul din stânga al Lightroom. Recomandat când lucrezi la un proiect specific, pentru a evita confuzii cu sesiuni foto diferite care pot avea numere identice.

#### Entire catalog

Caută în tot catalogul Lightroom. Util dacă nu știi exact în ce folder se află pozele sau dacă selecția clientului acoperă mai multe sesiuni.

> **Sfat:** Dacă ai sesiuni foto diferite cu numere care se repetă (de exemplu două sesiuni au ambele un fișier `0042`), folosește opțiunea cu folderul selectat pentru a evita marcarea pozei greșite.

---

### 3.4 File types to include — Tipuri de fișiere

Bifele din această secțiune îți permit să controlezi *ce tipuri de fișiere* vor fi marcate, indiferent de câte potriviri găsește plugin-ul.

| Bifă | Fișiere incluse |
|---|---|
| **RAW (CR2/NEF/ARW…)** | Fișiere RAW — Canon CR2/CR3, Nikon NEF, Sony ARW, Olympus ORF, etc. |
| **DNG** | Fișiere Adobe DNG standard |
| **DNG (HDR)** | Fișiere DNG cu sufixul `-HDR` sau `_HDR` în nume (ex. `C86A0042-HDR.dng`) |
| **JPG** | Fișiere JPEG (`.jpg`, `.jpeg`) |
| **Other** | Orice alt tip de fișier din catalog |

**Exemplu practic:** Ai fotografiat RAW+JPG. Ai livrat JPEG-urile clientului. Vrei să marchezi doar RAW-urile corespunzătoare selecției. Debifează **JPG** — plugin-ul va marca doar fișierele RAW, chiar dacă găsește și JPEG-uri cu același număr.

---

### 3.5 Action — Acțiunea aplicată

Alege ce se întâmplă cu pozele găsite.

#### Set star rating — Setează stele

Bifează și alege din meniu câte stele să primească pozele: 1 până la 5, sau „No rating" pentru a șterge stele existente.

#### Set color label — Setează etichetă de culoare

Bifează și alege culoarea: Roșu, Galben, Verde, Albastru, Violet, sau „None" pentru a șterge eticheta.

Poți bifa una sau ambele opțiuni simultan.

---

### 3.6 Preview și Apply

#### Butonul Preview

Înainte de a aplica orice modificare, apasă **Preview**. Plugin-ul:

1. Citește selecția clientului și extrage numerele.
2. Caută în domeniul selectat.
3. Afișează rezultatul sub formă de text:

```
12 photo(s) matched (searched 847 in selected source)
```

Dacă unele numere nu au fost găsite:

```
10 photo(s) matched (searched 847 in selected source) — 2 number(s) not found
```

Un rezultat verde înseamnă că s-au găsit potriviri. Roșu înseamnă că nu s-a găsit nimic — verifică prefixul, numărul de cifre și domeniul de căutare.

#### Butonul Apply

Apasă **Apply** (sau **OK**) pentru a aplica steaua și/sau eticheta pe pozele găsite. La final apare un mesaj de confirmare cu numărul de poze modificate și lista numerelor care nu au fost găsite (dacă există).

> Dacă apeși **Apply** fără să fi rulat mai întâi **Preview**, plugin-ul rulează automat căutarea înainte de a aplica.

---

## 4. Flux de lucru pas cu pas

**Situație:** Clientul ți-a trimis un mesaj cu selecția: *„Vreau 155, 175, 245 și 320."*

1. Deschide **Lightroom Classic**, mergi la modulul **Library**.
2. În panoul stâng, selectează folderul sesiunii foto respective.
3. Din meniu: **Library → Plugin Extras → Photo File Selector…**
4. În **Client Selection**, lipește mesajul clientului în căsuța de text.
5. Verifică că **Prefix** este corect (ex. `C86A`) și **Sequence digits** este `4`.
6. La **Search Scope**, lasă bifat **Currently selected folder / collection**.
7. La **File types to include**, debifează **JPG** dacă vrei să marchezi doar RAW-urile.
8. La **Action**, bifează **Set star rating** și alege `5 stars` (sau altă valoare).
9. Apasă **Preview** și verifică rezultatul.
10. Dacă totul arată bine, apasă **Apply**.

Pozele sunt acum marcate în Lightroom. Le poți găsi rapid cu un filtru după stele sau culoare.

---

## 5. Întrebări frecvente

**Plugin-ul nu găsește nicio poză deși numerele sunt corecte.**
Verifică prefixul — o literă greșită sau majusculă/minusculă diferită poate împiedica recunoașterea. Verifică și numărul de cifre. Încearcă să schimbi domeniul de căutare la **Entire catalog**.

**Clientul a trimis numere de 3 cifre (ex. `155`) dar fișierele mele au 4 cifre (`0155`).**
Nu e o problemă. Plugin-ul completează automat zerouri la stânga dacă numărul de cifre este mai mic decât cel setat în **Sequence digits**.

**Am fișiere cu sufixul `-HDR` și nu sunt marcate.**
Verifică că bifa **DNG (HDR)** este activată în secțiunea **File types to include**.

**Vreau să anulez marcajele aplicate.**
Lightroom are funcția **Edit → Undo** (`Ctrl+Z`) care poate anula modificările de metadate aplicate de plugin, dacă nu ai închis catalogul între timp. Alternativ, selectează manual pozele și șterge steaua/eticheta.

**Pot folosi plugin-ul fără să selectez un folder în prealabil?**
Da — alege **Entire catalog** la Search Scope și plugin-ul caută în tot catalogul.

---

## 6. Dezinstalare

1. **File → Plug-in Manager…**
2. Selectează **Photo File Selector** din listă.
3. Apasă **Remove**.
4. Șterge folderul `photo-selector-lr.lrplugin` de pe calculator.

---

*Plugin creat de [tryingtodoart](https://github.com/tryingtodoart) · Licență MIT · Cod sursă disponibil pe GitHub*
