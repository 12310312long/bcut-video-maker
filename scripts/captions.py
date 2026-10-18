"""Semantic caption boundaries; punctuation removal does not corrupt numbers."""
import re,unicodedata

DEFAULT_STROKE_LEVEL=10

def stroke_level(value=DEFAULT_STROKE_LEVEL):
    value=float(value)
    if not 0<value<=100:raise ValueError('Caption stroke_level must be greater than 0 and at most 100')
    return value

def display(text):
    text=re.sub(r'(?<=\d)：(?=\d)',':',text)
    out=[]
    for i,c in enumerate(text):
        prev=text[i-1] if i else '';nxt=text[i+1] if i+1<len(text) else ''
        numeric=prev.isdigit() and nxt.isdigit()
        keep=(c in '.:,' and numeric) or (c in '-/_' and prev.isalnum() and nxt.isalnum()) or (c=="'" and prev.isascii() and prev.isalpha() and nxt.isascii() and nxt.isalpha()) or c in '+-/%'
        if not unicodedata.category(c).startswith('P') or keep:out.append(c)
    return re.sub(r'\s+',' ',''.join(out)).strip()

def key(text):return re.sub(r'\s+','',display(text))

def sentences(text):
    last=0
    for i,c in enumerate(text):
        if c in '。！？.!?' and not (c=='.' and i and i+1<len(text) and text[i-1].isdigit() and text[i+1].isdigit()):
            yield text[last:i+1];last=i+1
    if text[last:]:yield text[last:]

def split(text,limit=22,editorial=None):
    text=re.sub(r'(?<=\d)：(?=\d)',':',text)
    if editorial is not None:
        result=[display(x) for x in editorial]
        assert ''.join(key(x) for x in result)==key(text),'editorial_cuts must preserve every spoken character'
        ends=[];pos=0
        for sentence in sentences(text):pos+=len(key(sentence));ends.append(pos)
        pos=0
        for line in result:
            end=pos+len(key(line));assert not any(pos<b<end for b in ends),'editorial cut crosses sentence boundary';pos=end
    else:
        result=[]
        for sentence in sentences(text):
            pieces=[display(x) for x in re.split(r'[，；：、“”「」]|(?<!\d)[,:;]|[,;](?!\d)',sentence) if key(x)]
            merged=[];i=0
            while i<len(pieces):
                piece=pieces[i];i+=1
                while len(key(piece))<4 and i<len(pieces) and len(key(piece+pieces[i]))<=limit:
                    piece+=(' ' if piece[-1:].isascii() and pieces[i][:1].isascii() else '')+pieces[i];i+=1
                if i==len(pieces) and len(key(piece))<2 and merged and len(key(merged[-1]+piece))<=limit:merged[-1]+=piece
                else:merged.append(piece)
            for piece in merged:
                if len(piece)<=limit:result.append(piece);continue
                # Prefer word boundaries for Latin text; balance CJK remainders.
                count=(len(piece)+limit-1)//limit;size=(len(piece)+count-1)//count
                while len(piece)>limit:
                    cut=piece.rfind(' ',max(2,size//2),limit+1)
                    if cut<2:cut=size
                    result.append(piece[:cut].strip());piece=piece[cut:].strip()
                if piece:result.append(piece)
    assert ''.join(key(x) for x in result)==key(text),'subtitle character loss'
    assert all(len(key(x))>=2 for x in result),'isolated character; provide editorial_cuts'
    assert all(len(x)<=limit for x in result),'caption too long; provide editorial_cuts'
    return result

def stamp(t,ass=False):
    n=round(t*(100 if ass else 1000))
    return f'{n//360000}:{n//6000%60:02}:{n//100%60:02}.{n%100:02}' if ass else f'{n//3600000:02}:{n//60000%60:02}:{n//1000%60:02},{n%1000:03}'
