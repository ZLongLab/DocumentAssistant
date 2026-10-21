"""Verify unique document overlaps before appending native screenshot pixels."""
from collections import Counter,defaultdict
from dataclasses import dataclass
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QPainter

_QUANTIZE=bytes(value//8 for value in range(256))
_COARSE=bytes(value//2 for value in range(256))
_BANDS=6


@dataclass(frozen=True)
class StitchResult:
    status:str
    added:int=0


def row_signatures(image,quantize=True):
    # Sample before conversion: converting a full 4K frame just to keep 160
    # columns wastes most of the capture budget. Fast scaling preserves samples.
    gray=image.scaled(160,image.height(),Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.FastTransformation)
    gray=gray.convertToFormat(QImage.Format.Format_Grayscale8)
    data=bytes(gray.constBits());stride=gray.bytesPerLine()
    # Byte translation runs in native code; do not loop over every sampled pixel.
    rows=[data[y*stride+8:y*stride+152] for y in range(gray.height())]
    return [row.translate(_QUANTIZE) for row in rows] if quantize else rows


def informative(row):return max(row)-min(row)>=3


def _tokens(row):
    if informative(row):yield -1,row
    width=len(row)//_BANDS
    for band in range(_BANDS):
        token=row[band*width:(band+1)*width].translate(_COARSE)
        if max(token)-min(token)>=2:yield band,token


def _row_array(rows):
    return np.frombuffer(b''.join(rows),dtype=np.uint8).reshape(len(rows),-1).astype(np.int16)


def _verify_sparse_edge(previous,current,shift):
    """Verify complete sparse content, optionally excluding a screen-edge fade.

    One short message in a mostly empty viewport cannot satisfy the dense-text
    row-span rule. It can still establish a seam when unique text rows and the
    entire remaining background agree. The only ignored area is a small suffix
    touching the physical bottom edge of one of the captured viewports.
    """
    if not isinstance(previous,np.ndarray):previous=_row_array(previous)
    if not isinstance(current,np.ndarray):current=_row_array(current)
    height=len(previous);overlap=height-abs(shift)
    if overlap<64:return None
    old_start,new_start=max(0,shift),max(0,-shift)
    a,b=previous[old_start:old_start+overlap],current[new_start:new_start+overlap]
    middle=a.shape[1]//2
    fg=(np.abs(a-np.partition(a,middle,axis=1)[:,middle,None])>=24)|(np.abs(b-np.partition(b,middle,axis=1)[:,middle,None])>=24)
    delta=np.abs(a-b);counts=fg.sum(axis=1)
    bad=np.flatnonzero((counts>0)&((((delta<=8)&fg).sum(axis=1)/np.maximum(1,counts)<.94)
                                  |((delta*fg).sum(axis=1)/np.maximum(1,counts)>6.)))
    stop=int(bad[0]) if len(bad) else overlap
    if overlap-stop>height*.18 or stop<max(64,overlap*.75):return None
    a,b,fg,delta=a[:stop],b[:stop],fg[:stop],delta[:stop]
    count=int(fg.sum())
    if count<64:return None
    # Background agreement is essential: a tiny copied phrase cannot link an
    # otherwise different page. This also checks low-contrast message bubbles.
    agreement=float(((delta<=8)&fg).sum())/count;difference=float((delta*fg).sum())/count
    if agreement<.99 or difference>1. or np.mean(delta<=8)<.995 or np.mean(delta)>.5:return None
    info=(np.ptp(a,axis=1)>=24)|(np.ptp(b,axis=1)>=24)
    exact=info&np.all(a==b,axis=1);ys=np.flatnonzero(exact)
    if len(ys)<8:return None
    columns=np.flatnonzero(fg[exact].any(axis=0))
    if len(columns)<4 or columns[-1]-columns[0]<12:return None
    # Unique whole rows, in both full viewports, exclude blank/repeated stripes.
    def runs(rows):
        counts=Counter();last=None
        for row in rows:
            key=row.astype(np.uint8).tobytes()
            # High-DPI rasterization can duplicate adjacent physical rows.
            # Repeated locations elsewhere in the document still count twice.
            if key!=last:counts[key]+=1
            last=key
        return counts
    old_counts,new_counts=runs(previous),runs(current)
    unique={row.astype(np.uint8).tobytes() for row in a[exact]
            if old_counts[row.astype(np.uint8).tobytes()]==new_counts[row.astype(np.uint8).tobytes()]==1}
    if len(unique)<8:return None
    return agreement,-difference,len(ys),shift


def _verify_occluded_rows(a,b,foreground,differences,ys,overlap,step,total,minimum,shift,photo=False):
    """Tolerate a few compact overlays without trusting an arbitrary patch.

    A chat viewport can have a fading footer AND an independent hover toolbar.
    Require the great majority of its informative rows and foreground to agree
    at one displacement; never let a fixed header alone establish a seam.
    """
    counts=foreground.sum(axis=1)
    tolerance=16 if photo else 8
    row_agreement=.90 if photo else .94
    row_error=8. if photo else 6.
    agreed=((differences<=tolerance)&foreground).sum(axis=1)
    errors=(differences*foreground).sum(axis=1)
    bad=np.flatnonzero((agreed/np.maximum(1,counts)<row_agreement)|(errors/np.maximum(1,counts)>row_error))
    intervals=[]
    for index in bad:
        y=int(ys[index])
        if intervals and y-intervals[-1][1]<=max(8,step*2):intervals[-1][1]=y
        else:intervals.append([y,y])
    if len(intervals)>3 or sum(end-start+step for start,end in intervals)>min(128,overlap*.25):return None
    retained=np.ones(len(a),dtype=bool)
    for start,end in intervals:retained&=(ys<start)|(ys>end)
    kept=ys[retained]
    if len(kept)<max(minimum,len(a)*.70) or kept[-1]-kept[0]<min(64,overlap*.60):return None
    if int(foreground[~retained].sum())>total*.30:return None
    fg=foreground[retained];delta=differences[retained];count=int(fg.sum())
    if count<32:return None
    agreement=float(((delta<=tolerance)&fg).sum())/count
    difference=float((delta*fg).sum())/count
    exact=int(np.count_nonzero(np.all(a[retained]==b[retained],axis=1)))
    if photo:
        # Resampled photographs can change every pixel slightly. Permit that
        # only for dense image content, with sub-two-level mean error and
        # virtually all foreground within sixteen levels. Text is not eligible.
        if np.median(fg.sum(axis=1))<a.shape[1]*.25 or len(kept)<60:return None
        if agreement<.995 or difference>2.:return None
    elif agreement<.94 or difference>6. or exact<12:return None
    return agreement,-difference,exact,shift


def _verify_shift(previous,current,shift):
    """Verify a candidate displacement with bounded repaint fallbacks.

    Keep the independent bands, local-occlusion limit and ambiguity check;
    speeding up acquisition must never turn a weak match into a valid seam.
    """
    height=len(previous);overlap=height-abs(shift)
    old_start,new_start=max(0,shift),max(0,-shift)
    if not isinstance(previous,np.ndarray):previous=_row_array(previous)
    if not isinstance(current,np.ndarray):current=_row_array(current)
    # Near zero, sparse sampling can alias duplicated high-DPI rows and turn a
    # hover repaint into a one-pixel scroll. Inspect every row in this case.
    step=1 if abs(shift)<=2 else max(1,overlap//200)
    ys=np.arange(0,overlap,step)
    a,b=previous[old_start+ys],current[new_start+ys]
    keep=(np.ptp(a,axis=1)>=24)|(np.ptp(b,axis=1)>=24)
    informative_rows=ys[keep];a,b=a[keep],b[keep]
    minimum=max(8,min(20,overlap//5))
    if len(informative_rows)<minimum or informative_rows[-1]-informative_rows[0]<min(64,overlap*.45):return None
    exact=int(np.count_nonzero(np.all(a==b,axis=1)))
    middle=a.shape[1]//2
    background_a=np.partition(a,middle,axis=1)[:,middle,None]
    background_b=np.partition(b,middle,axis=1)[:,middle,None]
    foreground=(np.abs(a-background_a)>=24)|(np.abs(b-background_b)>=24)
    differences=np.abs(a-b)
    shape=(len(a),_BANDS,-1)
    changed=((differences>8)&foreground).reshape(shape).any(axis=2)
    counts=foreground.reshape(shape).sum(axis=(0,2))
    agreed=((differences<=8)&foreground).reshape(shape).sum(axis=(0,2))
    errors=(differences*foreground).reshape(shape).sum(axis=(0,2))
    total=int(counts.sum())
    if total<32:return None
    # Discard at most one narrow vertical band, consistently for the whole
    # overlap. Picking the best band anew on each row can match unrelated text.
    worst=int(np.argmax(errors/np.maximum(1,counts)))
    bad=informative_rows[changed[:,worst]]
    local=not len(bad) or (len(bad)*step<=max(12,overlap*.20)
                       and bad[-1]-bad[0]<=max(32,overlap*.30))
    if local and counts[worst]<=total*.30:
        counts[worst]=0;agreed[worst]=0;errors[worst]=0
    agreed,count,error=int(agreed.sum()),int(counts.sum()),int(errors.sum())
    agreement=agreed/max(1,count);difference=error/max(1,count)
    if agreement<.94 or difference>6.:
        # The strict single-band check failed. Real chat pages can change two
        # separate areas at once (fixed footer fade plus message hover actions).
        # Check bounded row occlusions before the existing single-row fallback.
        robust=_verify_occluded_rows(a,b,foreground,differences,informative_rows,overlap,step,total,minimum,shift)
        if robust is not None:return robust
        # Chat message actions are a short horizontal row, often spanning
        # several bands. Ignore at most ONE compact changed row range, only
        # when enough independent content remains to verify the displacement.
        bad_rows=np.flatnonzero(((differences>8)&foreground).any(axis=1))
        if not len(bad_rows):return None
        first,last=bad_rows[0],bad_rows[-1]
        if informative_rows[last]-informative_rows[first]+step<=min(96,overlap*.15):
            # An alternative to vertical-band exclusion, not a cumulative mask.
            retained=np.ones(len(a),dtype=bool);retained[first:last+1]=False
            retained_y=informative_rows[retained]
            if (int(foreground[~retained].sum())<=total*.30 and len(retained_y)>=minimum
                    and retained_y[-1]-retained_y[0]>=min(64,overlap*.45)):
                fg=foreground[retained];delta=differences[retained];count=int(fg.sum())
                if count>=32:
                    agreement=float(((delta<=8)&fg).sum())/count
                    difference=float((delta*fg).sum())/count
                    if agreement>=.94 and difference<=6.:
                        exact=int(np.count_nonzero(np.all(a[retained]==b[retained],axis=1)))
                        return agreement,-difference,exact,shift
        photographic=_verify_occluded_rows(a,b,foreground,differences,informative_rows,overlap,step,total,minimum,shift,photo=True)
        if photographic is not None:return photographic
        if abs(shift)>=3:
            # Fractional browser scroll offsets can snap one text line to the
            # adjacent raster row while all other lines move by the main shift.
            # Verify those few rows at +/-1; never resample exported pixels or
            # allow this to turn an actual 1px move into a stationary frame.
            variants=np.stack((b,current[new_start+np.maximum(0,informative_rows-1)],
                                  current[new_start+np.minimum(overlap-1,informative_rows+1)]))
            choice=np.abs(variants-a[None,:,:]).sum(axis=2).argmin(axis=0)
            if np.count_nonzero(choice)<=len(a)*.25:
                adjusted=variants[choice,np.arange(len(a))]
                background=np.partition(adjusted,middle,axis=1)[:,middle,None]
                fg=(np.abs(a-background_a)>=24)|(np.abs(adjusted-background)>=24)
                adjusted_result=_verify_occluded_rows(a,adjusted,fg,np.abs(a-adjusted),informative_rows,overlap,step,int(fg.sum()),minimum,shift)
                if adjusted_result is not None:return adjusted_result[0],adjusted_result[1],exact,shift
        return None
    return agreement,-difference,exact,shift


def vertical_shift(previous,current,raw_previous=None,raw_current=None):
    height=len(previous);overlap_min=max(48,min(128,height//12))
    max_shift=height-overlap_min
    if max_shift<1:return None
    raw_previous=raw_previous or [bytes(v*8 for v in row) for row in previous]
    raw_current=raw_current or [bytes(v*8 for v in row) for row in current]
    # Native screenshots normally contain many identical text rows. Locate
    # unique exact anchors first, avoiding six fuzzy-band hashes per row.
    # Repeated/blank rows cannot vote; ambiguous pages still go through the
    # full verifier rather than guessing from the expected scroll direction.
    exact_positions=defaultdict(list)
    for y,row in enumerate(raw_previous):exact_positions[row].append(y)
    exact_votes=Counter()
    for y in range(0,height,3):
        matches=exact_positions.get(raw_current[y],())
        if len(matches)==1:
            shift=matches[0]-y
            if abs(shift)<=max_shift:exact_votes[shift]+=1
    strongest=exact_votes.most_common(2)
    if strongest and strongest[0][1]>=12 and (len(strongest)==1 or strongest[0][1]>=strongest[1][1]*4):
        shift=strongest[0][0]
        # Independently verify foreground across the entire overlap. A local
        # unchanged header, cursor or tiny matching patch is insufficient.
        result=_verify_shift(raw_previous,raw_current,shift)
        if result is None:result=_verify_sparse_edge(raw_previous,raw_current,shift)
        if result is not None and result[2]>=12:
            return shift
    positions=defaultdict(list)
    for y,row in enumerate(previous):
        for key in _tokens(row):positions[key].append(y)
    votes=Counter()
    for y in range(0,height,max(1,height//450)):
        for key in _tokens(current[y]):
            matches=positions.get(key,())
            if not matches or len(matches)>12:continue
            weight=(2. if key[0]==-1 else 1.)/len(matches)
            for old in matches:
                shift=old-y
                if abs(shift)<=max_shift:votes[shift]+=weight
    # Verify the strongest unique anchors, not dozens of expensive weak guesses.
    shifts={0}
    for shift,count in votes.most_common(10):
        if count>=3:shifts.add(shift)
    candidates=[];rejected=[]
    raw_previous,raw_current=_row_array(raw_previous),_row_array(raw_current)
    for shift in shifts:
        result=_verify_shift(raw_previous,raw_current,shift)
        if result is not None:candidates.append(result)
        else:rejected.append(shift)
    # Only inspect sparse/background evidence if normal content matching could
    # not establish a seam, keeping photographic repaint matching responsive.
    if not candidates:
        for shift in rejected:
            result=_verify_sparse_edge(raw_previous,raw_current,shift)
            if result is not None:candidates.append(result)
    if not candidates:return None
    candidates.sort(reverse=True);best=candidates[0]
    if any(abs(other[3]-best[3])>2 and other[0]>=best[0]-.02 and other[1]>=best[1]-.35
           and other[2]>=best[2]*.8 for other in candidates[1:]):return None
    return best[3]


def frames_settled(previous,current):
    if previous is None or previous.size()!=current.size():return False
    if previous==current:return True
    return _verify_shift(row_signatures(previous,False),row_signatures(current,False),0) is not None


class VerticalStitcher:
    def __init__(self,first,max_height=20000,max_pixels=24000000):
        if first.isNull() or first.width()<80 or first.height()<80:
            raise ValueError('长截图区域至少需要 80 × 80 像素，请重新框选')
        if first.height()>max_height or first.width()*first.height()>max_pixels:
            raise ValueError('所选区域过大，请缩小范围')
        self.previous=first.copy();self.previous.setDevicePixelRatio(1)
        self.raw_signatures=row_signatures(self.previous,False)
        self.signatures=[row.translate(_QUANTIZE) for row in self.raw_signatures]
        self.parts=[self.previous];self.height=first.height()
        # Coordinates are relative to the initial viewport, not the document's
        # unknown absolute scroll position. The captured interval grows at both ends.
        self.position=0;self.top=0;self.bottom=first.height()
        self.max_height=max_height;self.max_pixels=max_pixels

    @property
    def width(self):return self.previous.width()

    def _update_reference(self,frame,raw,signatures):
        self.previous=frame.copy();self.previous.setDevicePixelRatio(1)
        self.raw_signatures=raw;self.signatures=signatures

    def append(self,frame):
        if frame.isNull() or frame.size()!=self.previous.size():return StitchResult('size_changed')
        if frame==self.previous:return StitchResult('unchanged')
        raw=row_signatures(frame,False)
        signatures=[row.translate(_QUANTIZE) for row in raw]
        if raw==self.raw_signatures:
            self._update_reference(frame,raw,signatures)
            return StitchResult('unchanged')
        shift=vertical_shift(self.signatures,signatures,self.raw_signatures,raw)
        if shift is None:return StitchResult('no_overlap')
        if shift==0:
            # A pause can still repaint text or fade hover controls. Once the
            # verifier confirms zero movement, track that latest appearance.
            # Do not add/rewrite output pixels or advance document coordinates.
            # Failed matches must never replace this trusted reference.
            self._update_reference(frame,raw,signatures)
            return StitchResult('unchanged')
        position=self.position+shift
        top=min(self.top,position);bottom=max(self.bottom,position+frame.height())
        added_top=self.top-top;added_bottom=bottom-self.bottom
        new_height=bottom-top
        if new_height>self.max_height or self.width*new_height>self.max_pixels:return StitchResult('limit')
        if added_top:self.parts.insert(0,frame.copy(0,0,frame.width(),added_top))
        if added_bottom:self.parts.append(frame.copy(0,frame.height()-added_bottom,frame.width(),added_bottom))
        self._update_reference(frame,raw,signatures);self.height=new_height
        self.position=position;self.top=top;self.bottom=bottom
        if added_top:return StitchResult('prepended',added_top)
        if added_bottom:return StitchResult('appended',added_bottom)
        return StitchResult('covered')

    def image(self):
        result=QImage(self.width,self.height,QImage.Format.Format_RGB32)
        if result.isNull():raise MemoryError('长图过大，无法分配图片内存')
        painter=QPainter(result);y=0
        for part in self.parts:painter.drawImage(0,y,part);y+=part.height()
        painter.end();result.setDevicePixelRatio(1);return result
