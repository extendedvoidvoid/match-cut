# Beat Sync Reality Check - Why Filtering Failed

## What We Tried (And Why It Failed)

### Attempt 1: Energy-Based Selection
**Idea:** Score all beats by loudness, pick top N
**Result:** All beats clustered in chorus ❌

### Attempt 2: Segment-Based Selection  
**Idea:** Divide into segments, pick strongest from each
**Result:** Still terrible ❌

## The Core Problem

**We've been trying to fix the WRONG thing.**

The problem isn't **"how do we select N beats from 150 detected beats?"**

The problem is **"why are we detecting 150 beats when there should only be 30-50?"**

---

## The Real Issue

Your spectral flux onset detection is **too sensitive** and picks up:
- ✅ Kick drums (what you want)
- ❌ Hi-hats (DON'T want)
- ❌ Snare hits (MAYBE want)
- ❌ Cymbals (DON'T want)
- ❌ Melodic elements (DON'T want)

**Trying to filter these AFTER detection doesn't work** because:
1. You can't tell kicks from hi-hats by energy alone
2. Sometimes hi-hats are louder than kicks
3. The frequency information is lost after onset detection

---

## What I've Done (Revert)

I've **reverted to the original simple approach**:
- Detect all onsets
- Use first N beats chronologically
- No filtering, no prioritization

**Why:** Because filtering made it worse, not better.

---

## The Real Solution

You have **two choices**:

### Option 1: Reduce Detection Sensitivity ⭐ EASIEST

**Increase the onset detection threshold** so it only picks up STRONG beats (kicks) and ignores weak beats (hi-hats).

**How:**
```typescript
// In detectOnsetsFromFlux, line ~257
// Current: Uses median-based threshold
// Change to: Use higher percentile

const percentile = 0.7 + (sensitivity * 0.25);  // 70-95th percentile
// Was: 0.5 + (sensitivity * 0.4)  // 50-90th percentile
```

**Effect:**
- Fewer onsets detected (30-60 instead of 150)
- Only strong beats survive
- Hi-hats naturally filtered out
- **Time to implement:** 5 minutes

**Downside:**
- Might miss some legitimate beats
- Need to adjust sensitivity slider

---

### Option 2: Low-Frequency Onset Detection ⭐⭐ BETTER

**Only detect onsets in bass frequencies** (20-250 Hz) where kick drums live.

**How:**
Add a simple low-pass filter before onset detection:

```typescript
// In detectBeatsWebAudio, before spectral flux computation
private lowPassFilter(audioBuffer: AudioBuffer, cutoffFreq: number): AudioBuffer {
  const context = new OfflineAudioContext(
    1, 
    audioBuffer.length, 
    audioBuffer.sampleRate
  );
  
  const source = context.createBufferSource();
  source.buffer = audioBuffer;
  
  const filter = context.createBiquadFilter();
  filter.type = 'lowpass';
  filter.frequency.value = cutoffFreq;  // e.g., 250 Hz
  filter.Q.value = 0.7;
  
  source.connect(filter);
  filter.connect(context.destination);
  source.start();
  
  return context.startRendering();
}

// Then in detectBeatsWebAudio:
const lowFreqAudio = await this.lowPassFilter(audioBuffer, 250);  // Only bass
const flux = this.computeSpectralFlux(lowFreqAudio, fftSize, hopSize);
```

**Effect:**
- Hi-hats (4000-8000 Hz) completely ignored
- Snares (200-2000 Hz) reduced
- Kicks (60-150 Hz) fully captured
- **Time to implement:** 30-45 minutes

**Benefit:**
- Solves the problem at the source
- No need for filtering afterward
- Clean, predictable results

---

### Option 3: Multi-Band Onset Detection ⭐⭐⭐ BEST (But Complex)

**Detect onsets separately in low/mid/high bands**, then combine with weighting.

**Time:** 6-8 hours (as planned in Phase 2/3)

**Only do this if:** Options 1 and 2 don't work

---

## Recommended Action Plan

### Step 1: Try Option 1 (5 minutes)
Increase the detection threshold to be more selective.

**Edit `lib/beatDetection.ts` line ~372:**
```typescript
const percentile = 0.7 + (sensitivity * 0.25);  // Higher threshold
```

**Test:** Should detect 50-80 beats instead of 150

---

### Step 2: If Still Too Many, Try Option 2 (45 minutes)
Add low-pass filtering before onset detection.

---

### Step 3: Add UI Control
Add a "Beat Focus" slider:
```
Beat Focus: [Kicks Only] ━━●━━━━━ [All Beats]
            Low-pass 250Hz      No filter
```

---

## Why This Approach Works

**Current flow (BROKEN):**
```
Audio → Detect ALL onsets (150) → Try to filter → Still picks hi-hats ❌
```

**Option 1 (SIMPLE):**
```
Audio → Higher threshold → Detect fewer onsets (50) → Use them all ✓
```

**Option 2 (BETTER):**
```
Audio → Low-pass filter (keeps bass) → Detect onsets → Only kicks found ✓✓
```

---

## Console Output to Watch For

### After Option 1:
```
✅ Onset Detection Complete:
   onsetsDetected: 60  ← Should be much lower than before
   avgInterval: 500ms  ← More consistent
```

### After Option 2:
```
🎵 Low-pass filtered audio (250 Hz cutoff)
✅ Onset Detection Complete:
   onsetsDetected: 35  ← Even fewer, cleaner
   avgInterval: 520ms
```

---

## The Lesson

**You can't fix bad detection with good filtering.**

If onset detection finds 150 events when there should be 30:
- ❌ Don't try to pick the "best" 30 from the 150
- ✅ Fix the detection to only find 30 in the first place

This is why **Phase 1 and Phase 2 both failed** - they tried to filter after the fact instead of improving detection.

---

## Next Steps

1. **Test the reverted code** - it's back to original behavior
2. **Try Option 1** (higher threshold) - 5 minutes
3. **If still failing, try Option 2** (low-pass filter) - 45 minutes
4. **Report results** so we can decide next move

The silver lining: We now understand the problem deeply and know exactly what needs to be fixed.

---

## Quick Implementation: Option 1 (Do This Now)

Open `lib/beatDetection.ts`, find line ~372 (in `calculateEnergyThreshold`):

**Change from:**
```typescript
const percentile = 0.5 + (sensitivity * 0.4); // 50-90th percentile
```

**Change to:**
```typescript
const percentile = 0.7 + (sensitivity * 0.25); // 70-95th percentile
```

**Test it.** This alone might fix everything.
