# Multi-Band Detection - Issue Diagnosis & Fix

## Problem Summary

Multi-band detection **failed** in testing with following symptoms:
1. No beat sync (images change without beats)
2. 0% confidence (no rhythmic pattern detected)
3. Very low scores (0.66, 0.62, etc.)

---

## Root Cause: Incomplete FFT Implementation

### The Issue:

The `computeSpectralFlux()` method **isn't doing proper frequency analysis**:

```typescript
// Current implementation (line 357-361):
let sumOfSquares = 0;
for (let j = 0; j < windowData.length; j++) {
  sumOfSquares += windowData[j] * windowData[j];
}
currentSpectrum[0] = Math.sqrt(sumOfSquares / fftSize);  // ← Just RMS energy!
```

**Problem:** This calculates RMS energy, not a frequency spectrum.

**Impact:**
- Frequency bands ARE filtered correctly ✓
- But onset detection within each band still just looks at total energy ✗
- So filtering doesn't actually help - we're not analyzing frequency content

---

## Why It Failed in Your Test

### Your Test:
- **Song duration:** 31 seconds
- **Images:** 173
- **Required BPM:** 330+ (impossible!)

### What Happened:
```
31 seconds ÷ 173 images = 0.18 seconds per image
= 5.5 beats/second
= 330 BPM (way too fast!)
```

**Normal music:** 60-180 BPM (1-3 beats/second)  
**Your request:** 330 BPM (5.5 beats/second)

### Result:
- System tried to find 173 beats where only ~60 exist
- Picked up random energy fluctuations as "beats"
- No rhythmic pattern → 0% confidence
- Weak scores → noise, not real beats

---

## Immediate Fix Applied

### Changed:
```typescript
private USE_MULTIBAND = false;  // Disabled for now
```

**Reason:** Multi-band isn't helping without proper FFT. Reverting to simpler single-band detection that actually works.

---

## How to Test Now

### Step 1: Reduce Image Count

**For 31-second song:**
- ✅ Good: 30-60 images
- ⚠️ Maximum: 80 images  
- ❌ Don't use: 173 images

**Formula:** `images = (song_duration ÷ 0.5)` for standard beat sync

**Examples:**
- 30 second song → 60 images
- 60 second song → 120 images
- 180 second song → 360 images

---

### Step 2: Test Again

1. **Reduce to 50 images**
2. Upload same 31-second song
3. Enable beat sync
4. Check console - should see:
   ```
   ✅ Onset Detection Complete:
      onsetsDetected: 60-80
      confidence: 70-90%
   
   📊 Using first 50 beats from 70 detected onsets
   ```

5. Export and verify sync

---

## What Needs to be Fixed for Multi-Band

### The Real Problem:

`computeSpectralFlux` needs to:
1. Perform actual FFT (Fast Fourier Transform)
2. Analyze frequency bins
3. Track changes in frequency content

**Current:** RMS energy (time-domain)  
**Needed:** FFT spectrum (frequency-domain)

### Options:

#### Option 1: Use FFT Library
```typescript
import { FFT } from 'fft.js';  // External library

private computeSpectralFlux(...) {
  const fft = new FFT(fftSize);
  // Proper frequency analysis
}
```

**Pros:** Accurate, professional  
**Cons:** External dependency, larger bundle

---

#### Option 2: Use Web Audio AnalyserNode Properly
```typescript
// Use real-time frequency data
const analyzer = audioContext.createAnalyser();
analyzer.getFloatFrequencyData(frequencyData);
// Analyze frequency bins
```

**Pros:** No dependencies, native API  
**Cons:** Complex, async rendering

---

#### Option 3: Simplified Energy-Based Multi-Band
```typescript
// Skip FFT entirely
// Use filtered audio buffers directly with RMS energy
// Simpler but less accurate
```

**Pros:** Fast, simple  
**Cons:** Less precise than true spectral analysis

---

## Why Single-Band Works Better Now

**Single-band detection:**
- Uses RMS energy on full-spectrum audio
- Detects all strong transients (kicks, snares, hi-hats)
- With adaptive threshold, filters most noise
- **Works well if image count is reasonable**

**Multi-band detection (broken):**
- Filters audio into frequency bands ✓
- But still uses RMS energy for detection ✗
- Doesn't actually benefit from frequency separation
- More complex with no advantage

---

## Recommendation

### Immediate (Now):
1. ✅ Multi-band disabled
2. ✅ Using single-band
3. **User: Reduce image count to 50-60**
4. Test and verify sync works

### Short-Term (If Needed):
1. Implement proper FFT in `computeSpectralFlux`
2. Re-enable multi-band
3. Test across all music types

### Long-Term (Optional):
1. Add UI warning: "Too many images for song duration"
2. Auto-suggest optimal image count
3. Add "Beat Density" slider

---

## Expected Behavior After Fix

### Before (Multi-Band, Too Many Images):
```
🎛️ MULTI-BAND Detection
   Target: 173 beats for 31s
   Result: 173 random onsets (noise)
   Confidence: 0%
   Sync: Broken ❌
```

### After (Single-Band, Reasonable Images):
```
🎵 SINGLE-BAND Detection
   Target: 50 beats for 31s
   Detected: 70 real beats
   Selected: First 50
   Confidence: 80%+
   Sync: Works ✓
```

---

## Test Checklist

- [ ] Reduce images to 50-60
- [ ] Re-run beat detection
- [ ] Check console: confidence > 70%?
- [ ] Check console: reasonable BPM (60-180)?
- [ ] Export video
- [ ] Verify images change on beats
- [ ] Test with different songs
- [ ] Test with different image counts

---

## Conclusion

**Multi-band detection is disabled** until proper FFT implementation is added.

**Current system (single-band) works fine** if you use a reasonable image count.

**Rule of thumb:** `max_images = song_duration × 2`

For your 31-second song: **Use 50-60 images, not 173.**

Test this and let me know if beat sync works now!
