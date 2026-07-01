# Export Progress Tracking Fix

## Problem

The encoding progress bar was jumping to 30% instantly and then staying frozen until the export suddenly completed. This happened because:

1. **No FFmpeg progress monitoring** - The code set progress to 30% once and never updated it
2. **Missing real-time updates** - FFmpeg was encoding in the background without reporting progress
3. **Poor user experience** - Users couldn't tell if export was actually working or stuck

### Before Fix
```
Preparing frames: 0% → 30% (gradual)
Encoding video: 30% (stays frozen for 10-60 seconds)
Finalizing: 90% (instant jump)
Complete: 100%
```

## Solution

Added real-time FFmpeg progress event listeners that track actual encoding progress.

### Implementation

#### 1. Updated VideoExportProgress Type
Added optional `message` field to show detailed status:

```typescript
export interface VideoExportProgress {
  phase: 'preparing' | 'encoding' | 'finalizing' | 'complete';
  progress: number;
  frameCount?: number;
  currentFrame?: number;
  message?: string; // NEW: For detailed status like "Encoding: 5.2s / 25.5s"
}
```

#### 2. Added FFmpeg Progress Handler (MP4)
```typescript
const progressHandler = ({ progress, time }: { progress: number; time: number }) => {
  // FFmpeg reports time in microseconds
  const currentTime = time / 1000000;
  
  // Map encoding progress from 30% to 90% of overall progress
  const encodingProgress = Math.min(currentTime / totalDuration, 1);
  const overallProgress = 0.3 + (encodingProgress * 0.6);
  
  onProgress?.({ 
    phase: 'encoding', 
    progress: overallProgress,
    message: `Encoding: ${currentTime.toFixed(1)}s / ${totalDuration.toFixed(1)}s`
  });
};

this.ffmpeg.on('progress', progressHandler);
```

#### 3. Added Progress Handler for GIF Export
Same pattern for GIF exports:
```typescript
const gifProgressHandler = ({ progress, time }: { progress: number; time: number }) => {
  const currentTime = time / 1000000;
  const encodingProgress = Math.min(currentTime / totalDuration, 1);
  const overallProgress = 0.3 + (encodingProgress * 0.6);
  
  onProgress?.({ 
    phase: 'encoding', 
    progress: overallProgress,
    message: `Encoding GIF: ${currentTime.toFixed(1)}s / ${totalDuration.toFixed(1)}s`
  });
};
```

#### 4. Cleanup Event Listeners
Properly remove listeners after encoding to prevent memory leaks:
```typescript
try {
  await this.ffmpeg.exec(ffmpegArgs);
} finally {
  this.ffmpeg.off('progress', progressHandler);
}
```

#### 5. Updated UI to Show Message
```tsx
{exportProgress.message && (
  <div className="text-xs text-blue-700 text-center">
    {exportProgress.message}
  </div>
)}
```

## Progress Mapping

The overall export progress is divided into phases:

| Phase | Progress Range | Duration | What's Happening |
|-------|---------------|----------|------------------|
| **Preparing** | 0% → 30% | ~1-5s | Writing PNG frames to FFmpeg virtual filesystem |
| **Encoding** | 30% → 90% | ~5-60s | FFmpeg encoding video/GIF with real-time updates |
| **Finalizing** | 90% → 100% | ~1-2s | Reading output, cleanup, download |

### Why 30-90% for Encoding?

- Preparing frames is predictable (30% of work)
- **Encoding is the heavy operation** (60% of work) - needs detailed tracking
- Finalizing is quick (10% of work)

## After Fix

```
Preparing frames: 0% → 30% (gradual, frame by frame)
Encoding video: 30% → 35% → 45% → 60% → 75% → 90% (smooth, real-time)
  Message: "Encoding: 12.3s / 25.5s"
Finalizing: 90% → 100%
Complete: 100%
```

## Technical Details

### FFmpeg Progress Events

FFmpeg.wasm emits `progress` events during encoding:
```typescript
{
  progress: 0.48,    // Overall progress (0-1) - less reliable
  time: 12300000     // Microseconds processed - more reliable
}
```

We use `time` instead of `progress` because:
- **More accurate** for variable frame durations (beat sync)
- **Matches total duration** we calculated from frames
- **Linear progression** instead of FFmpeg's internal estimates

### Event Listener Pattern

```typescript
// 1. Define handler with proper typing
const handler = ({ progress, time }: { progress: number; time: number }) => {
  // Update UI
};

// 2. Register listener
this.ffmpeg.on('progress', handler);

// 3. Execute FFmpeg
try {
  await this.ffmpeg.exec(args);
} finally {
  // 4. ALWAYS cleanup listener (even on error)
  this.ffmpeg.off('progress', handler);
}
```

## User Experience Improvements

### Before
- ❌ Progress bar stuck at 30%
- ❌ No indication if export is working
- ❌ Users think it's frozen
- ❌ May refresh page unnecessarily

### After
- ✅ Smooth progress from 30% → 90%
- ✅ Real-time time counter: "5.2s / 25.5s"
- ✅ Clear visual feedback
- ✅ User confidence that export is working

## Testing

To verify the fix works:

1. Upload 10+ images
2. Enable beat sync with a long song (20+ seconds)
3. Click "Export as MP4"
4. **Watch the encoding progress**:
   - Should smoothly progress from 30% to 90%
   - Message should update: "Encoding: 0.5s / 25.5s" → "Encoding: 25.5s / 25.5s"
   - No freezing at 30%

## Files Modified

- **`lib/videoExport.ts`**
  - Added `progressHandler` for MP4 export
  - Added `gifProgressHandler` for GIF export
  - Proper event listener cleanup

- **`lib/types.ts`**
  - Added `message?: string` to `VideoExportProgress`

- **`components/ExportOptions.tsx`**
  - Display progress message in UI
  - Fallback to frame count if no message

## Performance Notes

- **No performance impact** - FFmpeg already generates these events
- **Minimal overhead** - Just updating a React state variable
- **Better perceived performance** - Users see progress instead of waiting
- **No memory leaks** - Listeners properly cleaned up

## Future Enhancements

Could add:
- FPS counter during encoding
- Estimated time remaining
- Pause/cancel encoding
- Detailed FFmpeg log view (debug mode)
