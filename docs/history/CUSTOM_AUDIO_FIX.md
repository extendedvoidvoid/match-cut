# Custom Audio Trimming Fix

## Issue Found
The `createSynchronizedAudioTrack` method in `audioManager.ts` was copying the **entire source audio** at each frame position instead of trimming it to the frame duration.

### Bug Location
**File:** `lib/audioManager.ts`  
**Line:** ~207 (original)

**Original buggy code:**
```typescript
// This was copying ALL sourceData samples
for (let i = 0; i < sourceData.length && (samplePosition + i) < totalSamples; i++) {
  outputData[samplePosition + i] += sourceData[i] * audioSettings.volume;
}
```

**Problem:** If user uploads a 30-second audio file, it would copy all 30 seconds at each frame position, causing audio overlap and the full file to play.

## Fix Applied

**New code:**
```typescript
// Calculate how many samples to copy (trimmed to frame duration)
const maxSamplesToCopy = Math.min(
  sourceBuffer.length,
  Math.floor(frameDuration * sampleRate)
);

// Copy source audio to output buffer at calculated position (trimmed to frame duration)
for (let channel = 0; channel < sourceBuffer.numberOfChannels; channel++) {
  const sourceData = sourceBuffer.getChannelData(channel);
  const outputData = outputBuffer.getChannelData(channel);
  
  // Apply volume and copy samples (only up to frame duration)
  for (let i = 0; i < maxSamplesToCopy && (samplePosition + i) < totalSamples; i++) {
    outputData[samplePosition + i] += sourceData[i] * audioSettings.volume;
  }
}
```

**Solution:** Calculate the maximum samples to copy based on the frame duration, then only copy that amount. This ensures:
- If audio is longer than frame duration → trim to frame duration
- If audio is shorter than frame duration → use entire audio

## Examples After Fix

### Scenario 1: Long Audio
- **Upload:** 30-second audio file
- **Frame duration:** 0.2 seconds
- **Result:** Only first 0.2s of audio is extracted and played at each transition ✅

### Scenario 2: Short Audio  
- **Upload:** 0.1-second audio file
- **Frame duration:** 0.2 seconds
- **Result:** Entire 0.1s audio plays at each transition ✅

### Scenario 3: Exact Match
- **Upload:** 0.2-second audio file
- **Frame duration:** 0.2 seconds
- **Result:** Entire audio plays at each transition ✅

## Testing
**Test Audio Button:** ✅ Already worked correctly (uses `playSoundEffect` with maxDuration)  
**Export:** ✅ Now fixed to trim audio to frame duration

## Impact
This fix affects both:
- **Custom audio** (user-uploaded files)
- **Built-in audio** (click sounds) - though these were already short enough to not cause issues

Both now work identically and correctly trim to frame duration.
