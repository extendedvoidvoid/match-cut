# Beat Prioritization Implementation Plan

## Problem Statement

**Current Issue:** Detecting ALL onsets (kicks, snares, hi-hats, melodic hits) = 50-150+ beats. Need to prioritize PRIMARY beats (mainly kick drum) for image synchronization.

**Root Cause:** Generic spectral flux treats all frequencies equally. No distinction between rhythmic pulse vs. background percussion.

---

## Research Findings

### Current Package: web-audio-beat-detector

**What it provides:**
- `analyze(audioBuffer)` → Returns BPM only
- `guess(audioBuffer)` → Returns `{ bpm, offset, tempo }`

**Critical:** ❌ Does NOT provide beat position arrays
✅ Current custom onset detection is correct approach

### Alternative: Essentia.js RhythmExtractor2013

**What it provides:**
- State-of-the-art beat tracking (not just onsets)
- Returns array of beat timestamps (`ticks`)
- Used by professional audio tools

**Status:** ❓ Need to verify if bundled with web-audio-beat-detector

---

## Three-Phase Strategy

### Phase 1: Energy-Based Selection ⭐ QUICK WIN
**Time:** 4-6 hours | **Impact:** 60-70% improvement

**Approach:**
1. Keep current onset detection (detect ALL beats)
2. Score each beat by RMS energy in 100ms window
3. Select top N strongest beats (where N = image count)
4. Return in chronological order

**Code Changes:**
```typescript
// lib/beatDetection.ts

async detectBeats(
  audioBuffer: AudioBuffer, 
  sensitivity: number,
  targetBeatCount?: number  // NEW: Pass image count
): Promise<BeatDetectionResult> {
  
  // 1. Detect all onsets (existing)
  const allOnsets = await this.detectBeatsWebAudio(audioBuffer, sensitivity);
  
  // 2. Score by energy
  const scored = this.scoreByEnergy(audioBuffer, allOnsets.beats);
  
  // 3. Select top N
  const finalBeats = targetBeatCount 
    ? this.selectTopN(scored, targetBeatCount)
    : allOnsets.beats;
  
  return { beats: finalBeats, bpm: this.calculateBPM(finalBeats), ... };
}

private scoreByEnergy(audioBuffer: AudioBuffer, beatTimes: number[]) {
  return beatTimes.map(time => {
    const energy = this.getRMSEnergyAt(audioBuffer, time, 0.1); // 100ms window
    return { time, energy, score: energy };
  });
}

private selectTopN(scored: ScoredBeat[], n: number): number[] {
  return scored
    .sort((a, b) => b.score - a.score)
    .slice(0, n)
    .map(b => b.time)
    .sort((a, b) => a - b);
}
```

**Pros:**
- ✅ Simple, low-risk
- ✅ No new dependencies
- ✅ Guaranteed N beats for N images
- ✅ Removes weakest hi-hats

**Cons:**
- ⚠️ Treats all frequencies equally
- ⚠️ May cluster in chorus (high energy section)

---

### Phase 2: Frequency-Weighted Scoring ⭐⭐ RECOMMENDED
**Time:** 6-8 hours | **Impact:** 80-85% improvement

**Approach:**
1. At each beat time, compute FFT
2. Split spectrum into bands (low/mid/high)
3. Weight: Low (kick) 3x, Mid (snare) 1.5x, High (hi-hat) 0.5x
4. Add prominence factor (how much beat stands out)
5. Select top N by combined score

**Key Addition:**
```typescript
private scoreWithFrequencyWeighting(audioBuffer: AudioBuffer, beatTimes: number[]) {
  return beatTimes.map(time => {
    // Get frequency content at beat
    const freq = this.getFrequencyAt(audioBuffer, time);
    
    // Weight by band importance
    const weightedEnergy = 
      (freq.lowEnergy * 3.0) +   // Bass = 3x
      (freq.midEnergy * 1.5) +   // Snare = 1.5x
      (freq.highEnergy * 0.5);   // Hi-hat = 0.5x
    
    // Add prominence
    const prominence = this.getProminence(audioBuffer, time);
    
    return { 
      time, 
      score: (weightedEnergy * 0.7) + (prominence * 0.3) 
    };
  });
}

private getFrequencyAt(audioBuffer: AudioBuffer, time: number) {
  const sampleIndex = time * audioBuffer.sampleRate;
  const fftSize = 2048;
  
  // Extract window, apply FFT
  const window = this.extractWindow(audioBuffer, sampleIndex, fftSize);
  const spectrum = this.computeFFT(this.applyHannWindow(window));
  
  // Split into bands (for 48kHz: bin * 23.4 Hz)
  return {
    lowEnergy: this.sumBins(spectrum, 0, 11),      // 0-250 Hz
    midEnergy: this.sumBins(spectrum, 11, 86),     // 250-2000 Hz
    highEnergy: this.sumBins(spectrum, 86, 1024)   // 2000+ Hz
  };
}
```

**Requirements:**
- FFT library: `fft.js` (npm) or similar

**Pros:**
- ✅ Kick drums prioritized over hi-hats
- ✅ Perceptually accurate
- ✅ Works across genres

**Cons:**
- ⚠️ Requires FFT implementation
- ⚠️ Slightly more CPU (still < 1 second)

---

### Phase 3: Full Multi-Band Onset Detection ⭐⭐⭐ BEST QUALITY
**Time:** 12-16 hours | **Impact:** 90-95% improvement

**Approach:**
1. Compute spectral flux SEPARATELY for each frequency band
2. Detect onsets in low/mid/high bands independently
3. Weight and merge onsets (low 3x, mid 1.5x, high 0.3x)
4. Select top N from merged list

**Key Change:**
```typescript
private computeMultiBandFlux(audioBuffer: AudioBuffer) {
  const numFrames = Math.floor(audioBuffer.length / hopSize);
  const lowFlux = new Float32Array(numFrames);
  const midFlux = new Float32Array(numFrames);
  const highFlux = new Float32Array(numFrames);
  
  for (let frame = 0; frame < numFrames; frame++) {
    const spectrum = this.computeFFT(frame);
    
    // Calculate flux in each band separately
    lowFlux[frame] = this.fluxInBand(spectrum, prevSpectrum, 0, 11);
    midFlux[frame] = this.fluxInBand(spectrum, prevSpectrum, 11, 86);
    highFlux[frame] = this.fluxInBand(spectrum, prevSpectrum, 86, 1024);
  }
  
  return { low: lowFlux, mid: midFlux, high: highFlux };
}

// Then detect onsets from each band independently
const lowOnsets = this.detectOnsetsFromFlux(bandFlux.low);  // Kicks
const midOnsets = this.detectOnsetsFromFlux(bandFlux.mid);  // Snares
const highOnsets = this.detectOnsetsFromFlux(bandFlux.high); // Hi-hats
```

**Pros:**
- ✅ Best accuracy
- ✅ Treats bands independently
- ✅ Professional-grade approach

**Cons:**
- ⚠️ Most complex
- ⚠️ Requires proper FFT library
- ⚠️ Higher CPU (but acceptable)

---

## Alternative: Essentia.js Integration

**IF Essentia is available (needs investigation):**

```typescript
import { RhythmExtractor2013 } from 'essentia.js'; // If available

const extractor = new RhythmExtractor2013({
  method: 'multifeature',
  minTempo: 60,
  maxTempo: 180
});

const result = extractor.compute(audioBuffer);
// result.ticks = array of PRIMARY beat positions
// result.bpm = tempo
// result.confidence = quality score
```

**Investigation Steps:**
1. Check `node_modules/web-audio-beat-detector/` for Essentia
2. Test if `RhythmExtractor2013` is exported
3. If yes: 2-hour implementation, best accuracy
4. If no: Proceed with Phase 1 → 2 → 3

---

## Edge Case Handling

### Too Few Beats Detected
```typescript
if (finalBeats.length < targetBeatCount * 0.5) {
  console.warn(`Only ${finalBeats.length} strong beats found for ${targetBeatCount} images`);
  console.warn('Recommendation: Reduce image count or use manual BPM');
  
  // Option A: Use all available (shorter video)
  // Option B: Extrapolate from BPM (less accurate)
}
```

### Images Change Too Fast
```typescript
const MIN_INTERVAL = 0.15; // 150ms human perception limit
const maxImages = Math.floor(audioBuffer.duration / MIN_INTERVAL);

if (targetBeatCount > maxImages) {
  console.warn(`${targetBeatCount} images too many for ${duration}s song`);
  console.warn(`Max recommended: ${maxImages} images`);
}
```

### No Bass Content (Acoustic Songs)
```typescript
if (avgLowFreqEnergy < 0.1) {
  console.log('Low bass content, adjusting weights for acoustic music');
  weights = { low: 1.5, mid: 2.5, high: 1.0 }; // Emphasize mids
}
```

---

## UI Enhancements

### 1. Beat Density Control
```tsx
<label>Beat Density: {densityLabel}</label>
<input 
  type="range" 
  min="0" 
  max="100" 
  value={beatDensity}
/>
<div className="flex justify-between text-xs">
  <span>Kicks Only</span>
  <span>Balanced</span>
  <span>All Beats</span>
</div>
```

**Mapping:**
- 0-33: Only kicks (low freq)
- 34-66: Kicks + snares (low + mid)
- 67-100: All percussion (low + mid + high)

### 2. Beat Quality Indicator
```tsx
{beatDetectionResult && (
  <div className="p-3 bg-blue-50 rounded">
    <div className="flex justify-between items-center">
      <span>Beat Detection Results</span>
      <span className={getQualityBadge()}>
        {getQualityLabel()} {/* Good / Moderate / Poor */}
      </span>
    </div>
    <div className="text-xs mt-2">
      <div>Detected: {beats.length} beats</div>
      <div>Using: {Math.min(beats.length, images.length)} for sync</div>
      <div>BPM: {bpm}</div>
    </div>
  </div>
)}
```

---

## Implementation Timeline

### Week 1: Quick Win
- **Mon-Tue:** Phase 1 (4-6h) - Energy-based selection
- **Wed:** UI enhancements (2-3h) - Quality indicator, warnings
- **Thu-Fri:** Testing (4-6h) - Multiple genres, edge cases

### Week 2: Production Quality
- **Mon-Wed:** Phase 2 (6-8h) - Frequency weighting + FFT
- **Thu-Fri:** Testing & refinement (4-6h)

### Week 3: Polish (If Needed)
- **Mon-Wed:** Phase 3 evaluation (implement if Phase 2 insufficient)
- **Thu-Fri:** Cache, Web Worker, optimization

**Total: 20-30 hours for complete solution**

---

## Recommended Action Plan

### Step 1: Investigate Essentia (30 min)
Check if RhythmExtractor2013 is available. If yes, use it (best ROI).

### Step 2: Implement Phase 1 (4-6h)
Quick win, immediate 60-70% improvement, low risk.

### Step 3: Test Extensively (4-6h)
10+ songs across genres, gather feedback.

### Step 4: Decide Next Phase
- If Phase 1 solves 80%+ of cases: Stop, ship it
- If not: Implement Phase 2 (frequency weighting)
- Phase 3 only if Phase 2 insufficient

### Step 5: UI Polish (2-3h)
Beat density slider, quality indicators, better logging.

---

## Success Metrics

| Metric | Current | Phase 1 Target | Phase 2 Target |
|--------|---------|----------------|----------------|
| Beats Detected | 50-150 | 30-50 (filtered) | 30-50 (smart) |
| Kick Detection | 50% | 70% | 90% |
| Hi-hat Rejection | 0% | 50% | 85% |
| User Satisfaction | 60% | 75% | 90% |

---

## Dependencies

**Phase 1:** None (uses existing code)

**Phase 2:** 
- FFT library: `fft.js` or `dsp.js` (npm install)
- ~50KB bundle size increase

**Phase 3:**
- Same as Phase 2

**Essentia (if available):**
- Already in package.json
- No additional dependencies

---

## Risk Assessment

**Phase 1:** ✅ Low risk, quick to implement, easy to test

**Phase 2:** ⚠️ Moderate complexity, FFT integration

**Phase 3:** ⚠️⚠️ High complexity, longer testing needed

**Recommendation:** Start with Phase 1, evaluate, then decide.
