"""
POSOCO ISTS Transmission Charges PDF Parser  v5
================================================
Handles all known PDF layout variations from POSOCO billing PDFs.

Three DIC entry patterns:

A) Layout A — S.No + Name on same line:
   "10 Railways-NR-ISTS-UP" → NR → 130 → [values...]

B) Layout B normal — S.No alone, then Name, then Region:
   "46" → "DVC" → "ER" → 1066 → [values...]   (Sep 2025 onwards)

C) Layout B orphan — S.No alone immediately followed by Region (no name),
   AND separate orphan data blocks (Region → gnash → values, no S.No/name),
   with a matching orphan name list appearing elsewhere in the same section:
   
   Main column:  "43" → "ER" → 3540 → [West Bengal data]
                 Then later a block:  44\n45\n46...\nWest Bengal\nOdisha\nBihar...
   Data column:  "ER" → 2166 → [Odisha data]
                 "ER" → 4847 → [Bihar data]  ...etc.
   
   The first name in the orphan list (West Bengal) is already handled by the 
   nameless block, so skip it when pairing with orphan data blocks.
"""

import re
import sys

REGIONS = {'NR', 'WR', 'SR', 'ER', 'NER'}

BILATERAL_ONLY_FRAGMENTS = [
    'northern railways', 'north central railways',
    'rapp 7&8', 'adani renewable energy park',
    'acme solar', 'thdc india', 'holding seventeen', 'essel saurya',
    'adani power limited', 'mahan energen', 'netra wind',
    'bhavini', 'betam', 'jsw renew', 'renew solar',
    'ntpc, north karanpura', 'nhpc ltd',
    'adani solar energy', 'abc rj land', 'juniper green',
    'amp energy', 'luceo solar', 'bn hybrid', 'cannice',
    'shikhar surya', 'rajasthan solar park', 'holding four',
    'acme solar holdings pvt. ltd.-',
]

MONTH_NAMES = {
    'january':1,'february':2,'march':3,'april':4,'may':5,'june':6,
    'july':7,'august':8,'september':9,'october':10,'november':11,'december':12
}

def month_idx(year, month):
    return (year - 2021) * 12 + (month - 1)

def clean_num(s):
    s = str(s).strip().replace(',','').replace('\u20b9','').strip()
    if not s: return None
    try: return int(float(s))
    except: return None

def is_region(s): return s.strip() in REGIONS

def is_bilateral_only(name):
    n = name.lower()
    return any(f in n for f in BILATERAL_ONLY_FRAGMENTS)

NOISE_FRAGMENTS = [
    'usage based','balance ac','system charges','national component',
    'regional component','transformers component','ac-ubc','ac-bc',
    'nc-re','nc-hvdc','bilateral charges','total transmission',
    'charges payable','without waiver','gna+','gnash','(in mw)',
    'designated ists','billing month','transmission charges for',
    '\x0c','note:','accordingly','phase-i','urtdsm','phasor',
    'nldc','ntamc','as per cerc',
]
NOISE_EXACT = {
    'S.No','S.No.','Zone','Region','GNAsh','AC-UBC','AC-BC','NC-RE','NC-HVDC',
    'RC','TC','Total','Bilateral','Transmission','(₹)','C','B','Cha','Bi',
    'Bilate','National Component (₹)','Regional','Component','Transformers',
    'TOTAL','TOTAL AMOUNT','ARE','on','Regi','charges (₹)','component (₹)',
}

def strip_header_noise(lines):
    out = []
    for line in lines:
        l = line.strip()
        if not l or l in NOISE_EXACT: continue
        if any(f in l.lower() for f in NOISE_FRAGMENTS): continue
        out.append(l)
    return out

def split_into_sections(all_lines):
    sections, cur = [], []
    cur_mon = cur_yr = None
    for line in all_lines:
        m = re.search(r'billing month of\s+(\w+)[,\s]+(\d{4})', line, re.I)
        if m:
            mname = m.group(1).lower(); yr = int(m.group(2))
            if mname in MONTH_NAMES:
                if cur_mon and cur: sections.append((cur_mon, cur_yr, cur))
                cur_mon, cur_yr, cur = MONTH_NAMES[mname], yr, [line]
                continue
        cur.append(line)
    if cur_mon and cur: sections.append((cur_mon, cur_yr, cur))
    return sections

def _extract_fields(name, region, nums):
    """Convert name+region+nums into a DIC dict."""
    if not nums: return None
    empty = dict(ac_ubc=0,ac_bc=0,nc_re=0,nc_hvdc=0,rc=0,trx=0,bil=0)
    if is_bilateral_only(name):
        bil = 0
        for i in range(len(nums)-1):
            if nums[i] == nums[i+1] and nums[i] > 0:
                bil = nums[i]; break
        if bil == 0 and nums: bil = nums[0]
        return {**empty, 'name':name, 'region':region, 'gnash':0, 'bil':bil}
    if len(nums) < 6: return None
    gnash = nums[0] if nums[0] <= 20000 else 0
    vals  = nums[1:] if gnash else nums
    if len(vals) < 5: return None
    ac_ubc,ac_bc,nc_re,nc_hvdc,rc = vals[0],vals[1],vals[2],vals[3],vals[4]
    rest = vals[5:]
    expected = ac_ubc+ac_bc+nc_re+nc_hvdc+rc
    trx = 0
    if rest:
        if len(rest) == 1:
            if abs(rest[0]-expected)/max(expected,1) > 0.10: trx = rest[0]
        else:
            ct,ctot = rest[0],rest[-1]
            if ctot > 0 and abs(ctot-(expected+ct))/ctot < 0.10: trx = ct
    return {'name':name,'region':region,'gnash':gnash,
            'ac_ubc':ac_ubc,'ac_bc':ac_bc,'nc_re':nc_re,'nc_hvdc':nc_hvdc,
            'rc':rc,'trx':trx,'bil':0}

def _collect_nums_from(tokens, start):
    """Collect consecutive numbers from tokens[start], stopping at DIC start or name."""
    nums = []; j = start; n = len(tokens)
    while j < n:
        t = tokens[j].strip()
        if re.match(r'^\d{1,3}\s+[A-Za-z]',t): break
        if re.match(r'^\d{1,3}$',t):
            peek = tokens[j+1].strip() if j+1<n else ''
            if re.match(r'^[A-Za-z]',peek) and not is_region(peek): break
            if is_region(peek): break
        v = clean_num(t)
        if v is not None:
            nums.append(v); j+=1; continue
        if t and re.match(r'^[A-Za-z]',t) and t not in REGIONS: break
        j+=1
    return nums, j

def _find_nameless_blocks_raw(raw_lines):
    """
    Find S.No → Region → data blocks (no name between S.No and Region).
    Returns list of (sno, region, nums) in document order.
    """
    blocks = []
    i = 0
    while i < len(raw_lines):
        l = raw_lines[i].strip()
        if re.match(r'^\d{1,3}$', l):
            sno = int(l)
            # Next non-empty line should be a Region
            j = i + 1
            while j < len(raw_lines) and not raw_lines[j].strip(): j+=1
            if j < len(raw_lines) and is_region(raw_lines[j]):
                region = raw_lines[j].strip()
                k = j+1
                nums = []
                while k < min(j+50, len(raw_lines)):
                    s = raw_lines[k].strip()
                    if is_region(s): break
                    if s and re.match(r'^[A-Za-z]',s) and clean_num(s) is None: break
                    v = clean_num(s)
                    if v is not None: nums.append(v)
                    k+=1
                if len(nums) >= 6:
                    blocks.append((sno, region, nums))
                    i = k; continue
        i+=1
    return blocks

def _find_orphan_data_blocks_raw(raw_lines):
    """
    Find Region → gnash → data blocks that have a large number (total) immediately before them.
    These appear when pdftotext serializes table columns separately.
    Returns list of (region, nums) in document order.
    """
    blocks = []
    for i,line in enumerate(raw_lines):
        l = line.strip()
        if l not in REGIONS: continue
        prev = ''
        for k in range(i-1, max(0,i-5), -1):
            if raw_lines[k].strip():
                prev = raw_lines[k].strip(); break
        pv = clean_num(prev)
        if not (pv and pv > 1000): continue
        region = l; j = i+1; nums = []
        while j < min(i+50, len(raw_lines)):
            s = raw_lines[j].strip()
            if is_region(s): break
            if s and re.match(r'^[A-Za-z]',s) and clean_num(s) is None: break
            v = clean_num(s)
            if v is not None: nums.append(v)
            j+=1
        # Accept full AC-charge blocks (>=6 nums) OR bilateral-only blocks (val repeated)
        is_bilateral_block = (len(nums) >= 2 and nums[0] == nums[1] and nums[0] > 0)
        if len(nums) >= 6 or is_bilateral_block:
            blocks.append((region, nums))
    return blocks

def _find_orphan_name_list_raw(raw_lines):
    """
    Find the orphan name list: consecutive S.No integers followed by DIC names.
    Returns (names_list, first_sno).
    """
    tokens = strip_header_noise(raw_lines)
    n = len(tokens)
    i = 0
    while i < n:
        t = tokens[i].strip()
        if re.match(r'^\d{1,2}$', t):
            j = i; snos = []
            while j<n and re.match(r'^\d{1,2}$', tokens[j].strip()):
                snos.append(int(tokens[j])); j+=1
            if len(snos) < 3: i+=1; continue
            names = []
            while j < n:
                s = tokens[j].strip()
                if not s: j+=1; continue
                if clean_num(s) is not None or is_region(s): break
                if re.match(r'^\d{1,3}\s+[A-Za-z]',s): break
                names.append(s); j+=1
            if len(names) >= 3:
                return names, snos[0]
        i+=1
    return [], 0

def parse_section(raw_lines, month, year):
    """Full section parser combining all three layout patterns."""
    tokens = strip_header_noise(raw_lines)
    n = len(tokens)
    results = []
    seen_names = set()

    def emit(dic):
        if dic and dic['name'] not in seen_names:
            dic['month']=month; dic['year']=year; dic['mi']=month_idx(year,month)
            results.append(dic)
            seen_names.add(dic['name'])

    # ── Pass 1: scan tokenized lines ─────────────────────────────────────
    i = 0
    while i < n:
        tok = tokens[i]

        # Layout A: "10 Railways-NR-ISTS-UP"
        m_a = re.match(r'^(\d{1,3})\s+([A-Za-z\(].*)$', tok)
        if m_a:
            name_part = m_a.group(2).strip(); j = i+1
            while j<n:
                nxt = tokens[j].strip()
                if is_region(nxt) or re.match(r'^\d+[,\.]', nxt): break
                if re.match(r'^\d{1,3}\s+[A-Za-z]',nxt) or re.match(r'^\d{1,3}$',nxt): break
                name_part=(name_part+' '+nxt).strip(); j+=1
            # Fix 2&3: prepend previous token if it's an orphaned name fragment
            # Rule: always look-back when the name contains a continuation marker like "(formerly"
            # which unambiguously indicates a mid-name S.No split.
            # For names starting with "(": always look-back (e.g. "(formerly Essar Power M.P.")
            # For other names: only look-back if prev_tok is a short fragment (not a full DIC name ending)
            if i > 0:
                prev_tok = tokens[i-1].strip()
                _name_is_continuation = (name_part.startswith('(') 
                    or '(formerly' in name_part.lower()
                    or name_part.lower().startswith('india ')
                    or name_part.lower().startswith('steel'))
                _complete_suffixes = ('pvt. ltd.', 'ltd.', 'pvt ltd')
                _prev_is_complete = any(prev_tok.lower().endswith(s) for s in _complete_suffixes)
                if (prev_tok and re.match(r'^[A-Za-z]', prev_tok)
                        and not is_region(prev_tok)
                        and not re.match(r'^\d', prev_tok)
                        and clean_num(prev_tok) is None
                        and (_name_is_continuation or not _prev_is_complete)):
                    name_part = prev_tok + ' ' + name_part
            name=re.sub(r'\s+',' ',name_part).strip()
            if j<n and is_region(tokens[j]):
                region=tokens[j]; j+=1
                nums,j2=_collect_nums_from(tokens,j)
                emit(_extract_fields(name,region,nums))
                j=j2
            i=j; continue

        # Layout B: standalone S.No
        if re.match(r'^(\d{1,3})$', tok):
            sno=int(tok); j=i+1
            while j<n and not tokens[j].strip(): j+=1
            if j>=n: i+=1; continue
            nxt=tokens[j].strip()

            if is_region(nxt):
                # Nameless block: S.No → Region directly (name comes from orphan list)
                region=nxt; j+=1
                nums,j2=_collect_nums_from(tokens,j)
                if len(nums)>=6:
                    # We'll fill the name in Pass 2; store as placeholder
                    results.append({'_nameless':True,'_sno':sno,'region':region,'nums':nums,
                                    'month':month,'year':year,'mi':month_idx(year,month)})
                j=j2; i=j; continue

            if re.match(r'^[A-Za-z]',nxt):
                name_part=nxt; j+=1
                while j<n:
                    nn=tokens[j].strip()
                    if is_region(nn) or re.match(r'^\d',nn): break
                    name_part=(name_part+' '+nn).strip(); j+=1
                name=re.sub(r'\s+',' ',name_part).strip()
                if j<n and is_region(tokens[j]):
                    region=tokens[j]; j+=1
                    nums,j2=_collect_nums_from(tokens,j)
                    emit(_extract_fields(name,region,nums))
                    j=j2
                i=j; continue
        i+=1

    # ── Pass 2: resolve nameless blocks and orphan data blocks ───────────
    nameless = [r for r in results if r.get('_nameless')]
    real_results = [r for r in results if not r.get('_nameless')]
    seen_names = {r['name'] for r in real_results}

    orphan_data = _find_orphan_data_blocks_raw(raw_lines)
    orphan_names, first_orphan_sno = _find_orphan_name_list_raw(raw_lines)

    # The nameless blocks correspond to: S.No=first_orphan_sno's DIC
    # (usually West Bengal, S.No 43 when orphan list starts at 44-51)
    # The orphan_names list: index 0 = first_orphan_sno - 1's DIC (the nameless block)
    #                         index 1+ = the orphan data blocks in order

    # Fill nameless block names
    if nameless and orphan_names:
        # The first name matches the first (and usually only) nameless block
        for idx, nb in enumerate(nameless):
            if idx < len(orphan_names):
                name = orphan_names[idx]
                dic = _extract_fields(name, nb['region'], nb['nums'])
                if dic:
                    dic['month']=month; dic['year']=year; dic['mi']=month_idx(year,month)
                    if name not in seen_names:
                        real_results.append(dic)
                        seen_names.add(name)

    # Orphan data blocks: only use ER/NER blocks for name-list pairing
    # (NR/WR bilateral blocks are handled by Pass 3)
    er_ner_orphan_data = [(r, nums) for r, nums in orphan_data if r in ('ER','NER')]
    if er_ner_orphan_data and orphan_names:
        # Determine how many names are "claimed" by nameless blocks
        n_nameless = len(nameless)
        remaining_names = [nm for nm in orphan_names[n_nameless:] if nm not in seen_names]
        for (region, nums), name in zip(er_ner_orphan_data, remaining_names):
            dic = _extract_fields(name, region, nums)
            if dic:
                dic['month']=month; dic['year']=year; dic['mi']=month_idx(year,month)
                if name not in seen_names:
                    real_results.append(dic)
                    seen_names.add(name)

    # ── Pass 3: match bilateral NR/WR orphan blocks with unresolved DIC names ────
    # Some bilateral DICs (THDC, Adani Seventeen) have their name in Layout-A token stream
    # but their data appears as NR orphan blocks. Identify them by:
    # (a) finding bilateral-only DIC names in the token stream that weren't parsed
    # (b) pairing with unmatched NR/WR orphan blocks in order
    nr_wr_orphan_blocks = [(r, nums) for r, nums in orphan_data
                           if r in ('NR','WR') and len(nums) >= 2 and nums[0] == nums[1]]
    if nr_wr_orphan_blocks:
        # Find bilateral-only DIC names in token stream not yet in seen_names
        unresolved_bilateral_names = []
        for i, tok in enumerate(tokens):
            # Layout A: S.No + name on same line
            m_a = re.match(r'^\d{1,3}\s+([A-Za-z\(].*)$', tok)
            # Layout B: standalone S.No, name on next line
            m_b = re.match(r'^(\d{1,3})$', tok) if not m_a else None
            if m_a:
                candidate = m_a.group(1).strip()
                j = i + 1
                while j < n:
                    nxt = tokens[j].strip()
                    if is_region(nxt) or re.match(r'^\d', nxt): break
                    candidate = (candidate + ' ' + nxt).strip(); j += 1
                candidate = re.sub(r'\s+', ' ', candidate).strip()
                if is_bilateral_only(candidate) and candidate not in seen_names:
                    if j >= n or not is_region(tokens[j]):
                        unresolved_bilateral_names.append((candidate, tok.split()[0]))
            elif m_b:
                j = i + 1
                while j < n and not tokens[j].strip(): j += 1
                if j >= n or is_region(tokens[j]) or not re.match(r'^[A-Za-z]', tokens[j]): continue
                candidate = tokens[j].strip(); j += 1
                while j < n:
                    nn = tokens[j].strip()
                    if is_region(nn) or re.match(r'^\d', nn): break
                    candidate = (candidate + ' ' + nn).strip(); j += 1
                candidate = re.sub(r'\s+', ' ', candidate).strip()
                if is_bilateral_only(candidate) and candidate not in seen_names:
                    if j >= n or not is_region(tokens[j]):
                        unresolved_bilateral_names.append((candidate, m_b.group(1)))
        for (name, sno), (region, nums) in zip(unresolved_bilateral_names, nr_wr_orphan_blocks):
            bil = nums[0] if (len(nums) >= 2 and nums[0] == nums[1]) else nums[0]
            dic = {'name': name, 'region': region, 'gnash': 0,
                   'ac_ubc':0,'ac_bc':0,'nc_re':0,'nc_hvdc':0,'rc':0,'trx':0,'bil':bil,
                   'month':month,'year':year,'mi':month_idx(year,month)}
            if name not in seen_names:
                real_results.append(dic)
                seen_names.add(name)

    # ── Pass 4: IPCL TC fallback ─────────────────────────────────────────────
    IPCL_TC = {range(48,56): 1933976, range(56,60): 3325915}
    for r in real_results:
        if 'India Power Corporation' in r.get('name','') and r.get('trx',0) == 0:
            for month_range, tc_val in IPCL_TC.items():
                if r['mi'] in month_range:
                    r['trx'] = tc_val

    return real_results

def _find_pdftotext():
    """Return path to pdftotext binary, or None if not found."""
    import shutil, os
    if shutil.which('pdftotext'):
        return 'pdftotext'
    poppler_env = os.environ.get('POPPLER_PATH', '')
    if poppler_env:
        for name in ('pdftotext.exe', 'pdftotext'):
            c = os.path.join(poppler_env, name)
            if os.path.isfile(c):
                return c
    if os.name == 'nt':
        drives = ['C:', 'D:']
        subdirs = [
            os.path.join('poppler', 'Library', 'bin'),
            os.path.join('poppler', 'bin'),
            os.path.join('Program Files', 'poppler', 'Library', 'bin'),
            os.path.join('Program Files', 'poppler', 'bin'),
            os.path.join('tools', 'poppler', 'bin'),
        ]
        for drive in drives:
            for sub in subdirs:
                loc = os.path.join(drive + os.sep, sub, 'pdftotext.exe')
                if os.path.isfile(loc):
                    return loc
    return None


def _extract_with_pdftotext(pdf_path, cmd):
    """Use pdftotext binary to extract text lines."""
    import subprocess, tempfile, os
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
        tmp_path = tmp.name
    try:
        subprocess.run([cmd, pdf_path, tmp_path],
                       check=True, capture_output=True)
        with open(tmp_path, encoding='utf-8', errors='replace') as f:
            return [l.rstrip() for l in f.readlines()]
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _extract_with_pymupdf(pdf_path):
    """Use PyMuPDF (fitz) to extract text lines. pip install pymupdf"""
    import fitz
    lines = []
    doc = fitz.open(pdf_path)
    for page in doc:
        text = page.get_text("text")
        if text:
            lines.extend(text.split('\n'))
        lines.append('')
    doc.close()
    return lines


def _extract_with_pdfplumber(pdf_path):
    """Use pdfplumber (pure Python) to extract text lines."""
    import pdfplumber
    lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=2)
            if text:
                lines.extend(text.split('\n'))
            lines.append('')
    return lines


def extract_text_from_pdf(pdf_path):
    """
    Extract text from a POSOCO PDF bill.

    Tries pdftotext first (faster, more accurate), then falls back to
    pdfplumber (pure Python, no external install needed).

    To install pdftotext:
      Windows : https://github.com/oschwartz10612/poppler-windows/releases
                set POPPLER_PATH=C:/poppler/Library/bin
      Linux   : sudo apt install poppler-utils
      Mac     : brew install poppler

    To install pdfplumber fallback:
      pip install pdfplumber
    """
    cmd = _find_pdftotext()
    if cmd:
        return _extract_with_pdftotext(pdf_path, cmd)

    # Fallback 1: PyMuPDF
    try:
        return _extract_with_pymupdf(pdf_path)
    except ImportError:
        pass
    # Fallback 2: pdfplumber
    try:
        return _extract_with_pdfplumber(pdf_path)
    except ImportError:
        raise RuntimeError(
            "No PDF extraction tool found.\n"
            "Install one of:\n"
            "  pip install pdfplumber          (easiest — pure Python)\n"
            "  OR install Poppler and set POPPLER_PATH:\\n\n"
            "    Windows: https://github.com/oschwartz10612/poppler-windows/releases\n"
            "    Linux:   sudo apt install poppler-utils\n"
            "    Mac:     brew install poppler"
        )


def parse_pdf_text(filepath, verbose=True):
    """
    Parse a POSOCO billing PDF or pre-extracted text file.
    Accepts .pdf (runs pdftotext automatically) or .txt (reads directly).
    Returns list of dicts:
      name, region, gnash, year, month, mi,
      ac_ubc, ac_bc, nc_re, nc_hvdc, rc, trx, bil
    """
    if filepath.lower().endswith('.pdf'):
        all_lines = extract_text_from_pdf(filepath)
    else:
        with open(filepath, encoding='utf-8', errors='replace') as f:
            all_lines = [l.rstrip() for l in f.readlines()]

    sections = split_into_sections(all_lines)
    if verbose:
        print(f"Found {len(sections)} month sections:")
        for mon,yr,sec in sections:
            print(f"  {list(MONTH_NAMES.keys())[mon-1].title()} {yr}: {len(sec)} lines")
    all_results = []
    for mon,yr,sec in sections:
        dics = parse_section(sec, mon, yr)
        if verbose:
            print(f"  → {list(MONTH_NAMES.keys())[mon-1].title()} {yr}: {len(dics)} DICs")
        all_results.extend(dics)
    return all_results

if __name__ == '__main__':
    fp = sys.argv[1] if len(sys.argv)>1 else '/tmp/2025_full.txt'
    results = parse_pdf_text(fp)
    print(f"\nTotal: {len(results)}")
    from collections import Counter
    for (yr,mon),cnt in sorted(Counter((r['year'],r['month']) for r in results).items()):
        print(f"  {list(MONTH_NAMES.keys())[mon-1].title()} {yr}: {cnt}")
