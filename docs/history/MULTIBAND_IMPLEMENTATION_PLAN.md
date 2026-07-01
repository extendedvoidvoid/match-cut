# Multi-Band Onset Detection - Full Implementation Plan

## Overview
Professional-grade beat detection that analyzes 5 frequency bands separately, just like Ableton Live and FL Studio.

**Time Estimate:** 6-8 hours  
**Complexity:** High  
**Benefit:** Works across ALL music types  

---

## Phase 1: Foundation (1-2 hours)

### Task 1.1: Create Biquad Filter Factory
**File:** `lib/audioFilters.ts` (NEW)
**What:** Create reusable Web Audio API filter functions
**Code:**
```typescript
export interface FilterConfig {
  type: 'lowpass' | 'highpass' | 'bandpass';
  frequency: number;
  Q?: number;
  sampleRate: number;
}

export class AudioFilter {
  static async applyFilter(
    audioBuffer: AudioBuffer, 
    config: FilterConfig
  ): Promise<AudioBuffer>
  
  static async createBandpassFilter(
    audioBuffer: AudioBuffer,
    lowFreq: number,
    highFreq: number
  ): Promise<AudioBuffer>
}
```

**Tests:**
- Filter 440 Hz sine wave with lowpass 200 Hz → should remove it
- Filter 100 Hz sine wave with highpass 200 Hz → should remove it
- Verify no audio distortion

**Dependencies:** None
**Output:** Working filter utility class

---

### Task 1.2: Define Frequency Bands
**File:** `lib/beatDetection.ts`
**What:** Add band configuration constants
**Code:**
```typescript
interface FrequencyBand {
  name: string;
  lowFreq: number;
  highFreq: number;
  weight: number;        // Priority multiplier
  description: string;   // What instruments live here
}

const FREQUENCY_BANDS: FrequencyBand[] = [
  { 
    name: 'sub-bass',
    lowFreq: 20,
    highFreq: 250,
    weight: 5.0,
    description: 'Kick drums, bass drops'
  },
  {
    name: 'low-mid',
    lowFreq: 250,
    highFreq: 500,
    weight: 3.0,
    description: 'Toms, bass guitar, low piano'
  },
  {
    name: 'mid',
    lowFreq: 500,
    highFreq: 2000,
    weight: 2.0,
    description: 'Snares, vocals, guitars'
  },
  {
    name: 'high-mid',
    lowFreq: 2000,
    highFreq: 8000,
    weight: 0.5,
    description: 'Hi-hats, cymbals'
  },
  {
    name: 'high',
    lowFreq: 8000,
    highFreq: 20000,
    weight: 0.2,
    description: 'Cymbals, air, sparkle'
  }
];
```

**Tests:**
- Verify bands cover full spectrum (20 Hz - 20 kHz)
- Verify no gaps or overlaps
- Weights sum check (optional)

**Dependencies:** None
**Output:** Band configuration ready

---

## Phase 2: Multi-Band Filtering (2-3 hours)

### Task 2.1: Implement Offline Audio Context Filtering
**File:** `lib/audioFilters.ts`
**What:** Use Web Audio API to filter audio buffer
**Technical:**
```typescript
async applyFilter(audioBuffer, config) {
  // Create offline context
  const offlineContext = new OfflineAudioContext(
    1,  // Mono (we'll use channel 0)
    audioBuffer.length,
    audioBuffer.sampleRate
  );
  
  // Create source
  const source = offlineContext.createBufferSource();
  source.buffer = audioBuffer;
  
  // Create filter
  const filter = offlineContext.createBiquadFilter();
  filter.type = config.type;
  filter.frequency.value = config.frequency;
  filter.Q.value = config.Q || 1.0;
  
  // Connect: source → filter → destination
  source.connect(filter);
  filter.connect(offlineContext.destination);
  
  // Render
  source.start(0);
  return await offlineContext.startRendering();
}
```

**Challenge:** BiquadFilter only does lowpass/highpass/bandpass single cutoff
**Solution:** For bandpass, cascade two filters:
```typescript
async createBandpassFilter(audioBuffer, lowFreq, highFreq) {
  // Step 1: High-pass at lowFreq (removes everything below)
  const highpassed = await this.applyFilter(audioBuffer, {
    type: 'highpass',
    frequency: lowFreq,
    Q: 0.7
  });
  
  // Step 2: Low-pass at highFreq (removes everything above)
  const bandpassed = await this.applyFilter(highpassed, {
    type: 'lowpass',
    frequency: highFreq,
    Q: 0.7
  });
  
  return bandpassed;
}
```

**Tests:**
- Generate test tones at 100 Hz, 500 Hz, 2000 Hz
- Apply bandpass 250-500 Hz
- Verify only 500 Hz tone remains

**Dependencies:** Task 1.1
**Output:** Working band-pass filter

---

### Task 2.2: Split Audio into 5 Bands
**File:** `lib/beatDetection.ts`
**What:** Create filtered version for each band
**Code:**
```typescript
private async splitIntoBands(
  audioBuffer: AudioBuffer
): Promise<Map<string, AudioBuffer>> {
  
  console.log('🎛️ Splitting audio into frequency bands...');
  
  const bands = new Map<string, AudioBuffer>();
  
  for (const band of FREQUENCY_BANDS) {
    console.log(`Filtering ${band.name} (${band.lowFreq}-${band.highFreq} Hz)...`);
    
    const filtered = await AudioFilter.createBandpassFilter(
      audioBuffer,
      band.lowFreq,
      band.highFreq
    );
    
    bands.set(band.name, filtered);
  }
  
  console.log('✅ All bands filtered');
  return bands;
}
```

**Performance:**
- 5 filters × 2 passes each = 10 filter operations
- Each takes ~200-500ms for 3-minute song
- Total: 2-5 seconds (acceptable)

**Tests:**
- Verify all 5 bands created
- Verify each band has same length as original
- Console shows progress

**Dependencies:** Task 2.1
**Output:** 5 filtered audio buffers

---

## Phase 3: Per-Band Onset Detection (1-2 hours)

### Task 3.1: Extract Onset Detection Logic
**File:** `lib/beatDetection.ts`
**What:** Make onset detection reusable for any audio buffer
**Refactor:**
```typescript
// Current method is hard-coded for full audio
private async detectBeatsWebAudio(audioBuffer, sensitivity)

// Refactor to:
private detectOnsetsInBuffer(
  audioBuffer: AudioBuffer,
  sensitivity: number,
  bandName?: string  // For logging
): number[]  // Array of timestamps
```

**What changes:**
- Remove beat prioritization (that comes later)
- Keep only: flux calculation → peak finding → timestamps
- Make it pure: input buffer → output timestamps
- Add bandName to console logs for debugging

**Tests:**
- Run on full audio → should return same as before
- Run on bass-filtered audio → should return fewer onsets

**Dependencies:** Task 2.2
**Output:** Reusable onset detection

---

### Task 3.2: Detect Onsets in Each Band
**File:** `lib/beatDetection.ts`
**What:** Run onset detection on all 5 bands
**Code:**
```typescript
interface BandOnset {
  time: number;      // Timestamp in seconds
  band: string;      // Which frequency band
  weight: number;    // Band importance
  energy: number;    // Local onset strength
}

private async detectMultiBandOnsets(
  bands: Map<string, AudioBuffer>,
  sensitivity: number
): Promise<BandOnset[]> {
  
  const allOnsets: BandOnset[] = [];
  
  for (const [bandName, buffer] of bands) {
    const bandConfig = FREQUENCY_BANDS.find(b => b.name === bandName)!;
    
    console.log(`🎵 Detecting onsets in ${bandName} band...`);
    
    // Detect onsets in this band
    const timestamps = this.detectOnsetsInBuffer(
      buffer,
      sensitivity,
      bandName
    );
    
    // Calculate energy for each onset
    const channelData = buffer.getChannelData(0);
    const sampleRate = buffer.sampleRate;
    
    for (const time of timestamps) {
      const energy = this.getEnergyAt(channelData, time, sampleRate);
      
      allOnsets.push({
        time,
        band: bandName,
        weight: bandConfig.weight,
        energy
      });
    }
    
    console.log(`  Found ${timestamps.length} onsets in ${bandName}`);
  }
  
  return allOnsets;
}
```

**Expected Results:**
```
🎵 Detecting onsets in sub-bass band...
  Found 45 onsets in sub-bass (kicks)
🎵 Detecting onsets in low-mid band...
  Found 23 onsets in low-mid (toms)
🎵 Detecting onsets in mid band...
  Found 67 onsets in mid (snares/vocals)
🎵 Detecting onsets in high-mid band...
  Found 230 onsets in high-mid (hi-hats)
🎵 Detecting onsets in high band...
  Found 180 onsets in high (cymbals)

Total: 545 onsets across all bands
```

**Tests:**
- EDM track: sub-bass should have regular kick pattern
- Orchestral: mid band should have most onsets
- Verify timestamps are in seconds (0.0 - duration)

**Dependencies:** Task 3.1
**Output:** Array of all onsets with band info

---

## Phase 4: Onset Scoring & Combination (1-2 hours)

### Task 4.1: Score Multi-Band Onsets
**File:** `lib/beatDetection.ts`
**What:** Calculate importance score for each onset
**Algorithm:**
```typescript
private scoreMultiBandOnset(onset: BandOnset): number {
  // Base score = band weight × local energy
  let score = onset.weight * onset.energy;
  
  // Bonus: Multiple bands firing at same time (within 50ms)
  // This indicates a "full spectrum hit" - very important
  const simultaneousBonus = this.countSimultaneousOnsets(onset);
  score *= (1 + simultaneousBonus * 0.2);  // Up to +100% boost
  
  return score;
}

private countSimultaneousOnsets(
  target: BandOnset,
  allOnsets: BandOnset[]
): number {
  const WINDOW = 0.05;  // 50ms window
  
  let count = 0;
  for (const other of allOnsets) {
    if (other.band !== target.band &&  // Different band
        Math.abs(other.time - target.time) < WINDOW) {
      count++;
    }
  }
  return count;
}
```

**Why Simultaneous Bonus?**
- Kick + snare at same time = major beat ↑
- Just hi-hat alone = minor beat ↓
- More bands = more important = human perception

**Tests:**
- Kick only: score = 5.0 × energy
- Kick + snare at same time: score = 5.0 × energy × 1.2 (20% bonus)
- Kick + snare + tom: score = 5.0 × energy × 1.4 (40% bonus)

**Dependencies:** Task 3.2
**Output:** Scored onsets

---

### Task 4.2: Merge Nearby Onsets
**File:** `lib/beatDetection.ts`
**What:** Combine onsets that happen within 50ms of each other
**Problem:** Same kick drum might trigger onset in BOTH sub-bass and low-mid
**Solution:** Group nearby onsets, keep highest score
**Code:**
```typescript
private mergeNearbyOnsets(
  onsets: BandOnset[],
  threshold: number = 0.05  // 50ms
): BandOnset[] {
  
  // Sort by time
  const sorted = [...onsets].sort((a, b) => a.time - b.time);
  
  const merged: BandOnset[] = [];
  let currentGroup: BandOnset[] = [];
  
  for (const onset of sorted) {
    if (currentGroup.length === 0) {
      currentGroup.push(onset);
      continue;
    }
    
    const lastTime = currentGroup[currentGroup.length - 1].time;
    
    if (onset.time - lastTime < threshold) {
      // Within threshold - add to group
      currentGroup.push(onset);
    } else {
      // Outside threshold - finalize group, start new
      merged.push(this.selectBestFromGroup(currentGroup));
      currentGroup = [onset];
    }
  }
  
  // Don't forget last group
  if (currentGroup.length > 0) {
    merged.push(this.selectBestFromGroup(currentGroup));
  }
  
  return merged;
}

private selectBestFromGroup(group: BandOnset[]): BandOnset {
  // Pick onset with highest score
  // OR combine scores and use average time
  return group.reduce((best, current) => 
    this.scoreMultiBandOnset(current) > this.scoreMultiBandOnset(best) 
      ? current 
      : best
  );
}
```

**Effect:**
```
Before merge: 545 onsets (many duplicates)
After merge: 85 onsets (unique beat positions)
```

**Tests:**
- Kick at 1.000s in sub-bass + kick at 1.020s in low-mid → merged to 1.000s
- Distant onsets stay separate
- Verify count reduction

**Dependencies:** Task 4.1
**Output:** Unique beat positions

---

### Task 4.3: Select Top N Beats
**File:** `lib/beatDetection.ts`
**What:** Pick N strongest beats for N images
**Code:**
```typescript
private selectTopMultiBandBeats(
  onsets: BandOnset[],
  targetCount?: number
): number[] {
  
  if (!targetCount || onsets.length <= targetCount) {
    // Use all onsets
    return onsets.map(o => o.time).sort((a, b) => a - b);
  }
  
  // Score all onsets
  const scored = onsets.map(onset => ({
    time: onset.time,
    score: this.scoreMultiBandOnset(onset, onsets)
  }));
  
  // Sort by score (highest first)
  scored.sort((a, b) => b.score - a.score);
  
  // Take top N
  const selected = scored.slice(0, targetCount);
  
  // Return in chronological order
  return selected
    .map(s => s.time)
    .sort((a, b) => a - b);
}
```

**Logic:**
- All beats already scored by band weight + energy + simultaneity
- Simply sort by score and take top N
- Natural selection (not segment-based)

**Tests:**
- 85 onsets, request 30 → should return 30 highest-scored
- Verify chronological order
- Log top 10 scores to console

**Dependencies:** Task 4.2
**Output:** Final beat array

---

## Phase 5: Integration (1 hour)

### Task 5.1: Wire Multi-Band into Main Flow
**File:** `lib/beatDetection.ts`
**What:** Replace single-band detection with multi-band
**Code:**
```typescript
private async detectBeatsWebAudio(
  audioBuffer: AudioBuffer,
  sensitivity: number,
  targetBeatCount?: number
): Promise<BeatDetectionResult> {
  
  console.log('🎵 Running MULTI-BAND onset detection...');
  
  // Step 1: Split into frequency bands
  const startFilter = performance.now();
  const bands = await this.splitIntoBands(audioBuffer);
  console.log(`⏱️ Filtering took ${(performance.now() - startFilter).toFixed(0)}ms`);
  
  // Step 2: Detect onsets in each band
  const startDetect = performance.now();
  const allOnsets = await this.detectMultiBandOnsets(bands, sensitivity);
  console.log(`⏱️ Detection took ${(performance.now() - startDetect).toFixed(0)}ms`);
  console.log(`📊 Total onsets: ${allOnsets.length}`);
  
  // Step 3: Merge nearby onsets
  const merged = this.mergeNearbyOnsets(allOnsets);
  console.log(`📊 After merge: ${merged.length} unique beats`);
  
  // Step 4: Select top N if needed
  const finalBeats = this.selectTopMultiBandBeats(merged, targetBeatCount);
  console.log(`📊 Selected beats: ${finalBeats.length}`);
  
  // Step 5: Calculate BPM and confidence
  const bpm = this.calculateBPMFromBeats(finalBeats);
  const confidence = this.calculateConfidence(finalBeats, bpm);
  
  console.log('✅ Multi-band detection complete:', {
    bandsAnalyzed: FREQUENCY_BANDS.length,
    totalOnsets: allOnsets.length,
    mergedOnsets: merged.length,
    selectedBeats: finalBeats.length,
    bpm: Math.round(bpm),
    confidence: (confidence * 100).toFixed(0) + '%'
  });
  
  return {
    beats: finalBeats,
    bpm: Math.round(bpm),
    confidence,
    duration: audioBuffer.duration
  };
}
```

**Tests:**
- Run on EDM track
- Run on Harry Potter
- Run on K'NAAN
- Verify all complete without errors

**Dependencies:** All previous tasks
**Output:** Working multi-band system

---

### Task 5.2: Add Feature Flag
**File:** `lib/beatDetection.ts`
**What:** Allow switching between single-band and multi-band
**Code:**
```typescript
private USE_MULTIBAND = true;  // Feature flag

async detectBeats(...) {
  if (this.USE_MULTIBAND) {
    return await this.detectBeatsMultiBand(...);
  } else {
    return await this.detectBeatsSingleBand(...);  // Old method
  }
}
```

**Why:** Easy rollback if something breaks

**Tests:**
- Toggle flag, verify both work
- Compare results

**Dependencies:** Task 5.1
**Output:** Safe deployment

---

## Phase 6: Testing & Optimization (1-2 hours)

### Task 6.1: Test Suite
**Test Cases:**

#### Test 1: EDM with Heavy Hi-Hats
```
File: videoplayback_JqY9iy9b.mp3 (from your screenshot)
Expected:
  - Sub-bass: ~50 onsets (kicks)
  - High-mid: ~300 onsets (hi-hats)
  - After scoring: Only kicks in top 30
  - No rapid hi-hat transitions
Success: ✓ if kicks detected, hi-hats filtered
```

#### Test 2: Harry Potter Orchestral
```
File: harry potter theme bgm ringtone.mp3
Expected:
  - Mid band: ~60 onsets (piano melody)
  - Sub-bass: ~20 onsets (low piano notes)
  - After scoring: Piano beats selected
  - Smooth sync to musical phrases
Success: ✓ if detects 40-60 beats, follows melody
```

#### Test 3: K'NAAN Dense Pop
```
File: KNAAN - Wavin' Flag.mp3
Expected:
  - Sub-bass: ~55 onsets (kicks throughout)
  - Mid: ~200 onsets (vocals/synths - ignored)
  - After scoring: Kick pattern clear
  - No clustering in chorus
Success: ✓ if kicks detected despite dense mix
```

#### Test 4: Clean Drum Loop
```
File: modern-soul-drum-loop-ride-dry-beat-80-bpm.mp3
Expected:
  - Clear detection in all relevant bands
  - No change from previous system
  - Still works perfectly
Success: ✓ if same or better than before
```

#### Test 5: Phase Effect Track
```
File: phase-beat-effect-409056.mp3 (your screenshot shows fade-out)
Expected:
  - Detects beats in active section
  - Doesn't detect noise in fade-out
  - Handles gradual energy loss
Success: ✓ if stops detecting when music stops
```

**Pass Criteria:** 5/5 tests succeed

---

### Task 6.2: Performance Optimization
**Measure:**
```typescript
console.time('Multi-band Detection');
// ... detection code ...
console.timeEnd('Multi-band Detection');
```

**Target:** < 10 seconds for 3-minute song

**If too slow, optimize:**
1. Reduce FFT size for high bands (less detail needed)
2. Cache filtered buffers
3. Parallel filtering (Promise.all)
4. Use Web Workers (advanced)

**Optimization order:**
```typescript
// Before: Sequential filtering
for (const band of bands) {
  filtered = await filter(band);
}

// After: Parallel filtering
const filtered = await Promise.all(
  bands.map(band => filter(band))
);
```

**Expected improvement:** 50% faster (5s → 2.5s)

---

### Task 6.3: Console Output Polish
**Add detailed logging:**
```
🎛️ Multi-Band Beat Detection
━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Audio: 187.2s, 48000 Hz, 2 channels

🎛️ Filtering frequency bands...
  ✓ Sub-bass (20-250 Hz)     - 487ms
  ✓ Low-mid (250-500 Hz)     - 445ms
  ✓ Mid (500-2000 Hz)        - 521ms
  ✓ High-mid (2000-8000 Hz)  - 398ms
  ✓ High (8000-20000 Hz)     - 412ms
⏱️ Total filtering: 2.26s

🎵 Detecting onsets...
  ✓ Sub-bass: 45 onsets (kicks)
  ✓ Low-mid: 23 onsets (toms)
  ✓ Mid: 67 onsets (snares)
  ✓ High-mid: 230 onsets (hi-hats)
  ✓ High: 180 onsets (cymbals)
📊 Total: 545 onsets

🔗 Merging nearby onsets (50ms window)...
📊 After merge: 85 unique beats

🎯 Scoring & selection...
📊 Top scores: [12.4, 11.8, 11.2, 10.9, 10.6]
📊 Selected: 30 beats for 30 images

✅ Multi-Band Detection Complete
━━━━━━━━━━━━━━━━━━━━━━━━━━
  Bands analyzed: 5
  Total time: 4.8s
  Beats detected: 30
  BPM: 128
  Confidence: 87%
```

---

## Phase 7: Documentation (30 min)

### Task 7.1: Update README
**File:** `MULTIBAND_BEAT_DETECTION.md` (NEW)
**Content:**
- How it works
- Frequency band breakdown
- Why it's better
- Performance characteristics
- Troubleshooting guide

### Task 7.2: Code Comments
**Add to all new functions:**
```typescript
/**
 * Multi-band onset detection
 * 
 * Splits audio into 5 frequency bands and detects onsets separately.
 * Bass frequencies (kicks) are weighted 5x higher than treble (hi-hats).
 * 
 * This approach works across all music types:
 * - EDM: Isolates kicks from hi-hats
 * - Orchestral: Detects piano/string patterns
 * - Dense pop: Finds kicks despite background vocals
 * 
 * @param audioBuffer - Audio to analyze
 * @param sensitivity - Detection sensitivity (0-1)
 * @param targetBeatCount - Optional: select top N beats
 * @returns Array of beat timestamps in seconds
 */
```

---

## Risk Assessment

### High Risk:
1. **Performance** - 5× filtering operations (2-5s added)
   - Mitigation: Parallel filtering, show progress bar
2. **Web Audio API Limits** - Browser memory constraints
   - Mitigation: Process in chunks if buffer > 10 minutes

### Medium Risk:
1. **Filter Artifacts** - Ringing, phase issues
   - Mitigation: Use appropriate Q values (0.7-1.0)
2. **Band Overlap** - Kick drum energy bleeding into low-mid
   - Mitigation: Accept overlap, scoring handles it

### Low Risk:
1. **Edge Cases** - Very short songs (< 10s)
   - Mitigation: Fallback to single-band
2. **Unusual Genres** - Death metal, drone
   - Mitigation: Scoring adapts naturally

---

## Rollback Plan

If multi-band fails in production:

1. Set `USE_MULTIBAND = false`
2. System falls back to previous adaptive single-band
3. Users see no disruption
4. Debug offline, re-deploy when fixed

---

## Success Criteria

**Multi-band detection is successful if:**
- ✅ Harry Potter: Detects 40-60 beats (piano pattern)
- ✅ EDM: Detects kicks only (no hi-hats)
- ✅ Dense pop: Finds kicks despite vocals
- ✅ Processing time: < 10 seconds
- ✅ No audio quality degradation
- ✅ Works offline (no external APIs)
- ✅ 5/5 test cases pass

---

## Timeline

```
Hour 0-2:  Phase 1 (Foundation)
Hour 2-5:  Phase 2 (Multi-Band Filtering)
Hour 5-7:  Phase 3 (Per-Band Detection)
Hour 7-9:  Phase 4 (Scoring & Combination)
Hour 9-10: Phase 5 (Integration)
Hour 10-12: Phase 6 (Testing & Optimization)
Hour 12-12.5: Phase 7 (Documentation)

Total: ~12 hours (with buffer)
Optimistic: 8 hours
Realistic: 10 hours
```

---

## Next Steps

1. ✅ Review this plan
2. ⏳ Confirm approach
3. ⏳ Start Phase 1: Foundation
4. ⏳ Implement step-by-step
5. ⏳ Test each phase before moving on
6. ⏳ Deploy and celebrate! 🎉

Ready to start?
