import { useEffect, useRef, useState, useCallback } from 'react';
import { Play, Pause, RotateCcw, Settings } from 'lucide-react';
import { AnimationFrame, ExportSettings } from '@/lib/types';
import { AudioManager } from '@/lib/audioManager';
import { cn } from '@/lib/utils';

interface AnimationPreviewProps {
  frames: AnimationFrame[];
  frameDuration: number;
  isPlaying: boolean;
  onPlayPause: () => void;
  onFrameChange?: (frameIndex: number) => void;
  audioSettings?: ExportSettings;
  audioManager?: AudioManager | null;
  className?: string;
  disabled?: boolean;
}

export default function AnimationPreview({
  frames,
  frameDuration,
  isPlaying,
  onPlayPause,
  onFrameChange,
  audioSettings,
  audioManager,
  className,
  disabled = false
}: AnimationPreviewProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number | undefined>(undefined);
  const [currentFrame, setCurrentFrame] = useState(0);
  const [lastFrameTime, setLastFrameTime] = useState(0);

  const drawFrame = useCallback((frameIndex: number) => {
    const canvas = canvasRef.current;
    if (!canvas || frames.length === 0) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const frame = frames[frameIndex];
    if (!frame) return;

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Draw frame
    ctx.drawImage(frame.canvas, 0, 0, canvas.width, canvas.height);
    
    // Draw frame indicator
    ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
    ctx.fillRect(10, 10, 60, 25);
    ctx.fillStyle = 'white';
    ctx.font = '12px sans-serif';
    ctx.fillText(`${frameIndex + 1}/${frames.length}`, 15, 27);
  }, [frames]);

  // Start/stop animation
  useEffect(() => {
    if (isPlaying && frames.length > 0) {
      let lastTime = performance.now();
      let frameIndexRef = currentFrame; // Track current frame in closure
      
      const animateFrame = (timestamp: number) => {
        if (!isPlaying || frames.length === 0) {
          animationRef.current = undefined;
          return;
        }

        // Use the ref value instead of stale state
        const currentFrameData = frames[frameIndexRef];
        const currentFrameDuration = currentFrameData?.duration || frameDuration;
        
        if (timestamp - lastTime >= currentFrameDuration * 1000) {
          // Update to next frame
          frameIndexRef = (frameIndexRef + 1) % frames.length;
          
          setCurrentFrame(frameIndexRef);
          onFrameChange?.(frameIndexRef);
          
          // Play sound effect on frame change
          if (audioManager && audioSettings?.addSound && audioSettings.format === 'mp4') {
            audioManager.playSoundEffect(
              audioSettings.soundType,
              audioSettings.builtinSound,
              audioSettings.customAudioFile,
              audioSettings.audioVolume,
              currentFrameDuration // Use actual frame duration
            );
          }
          
          lastTime = timestamp;
        }

        animationRef.current = requestAnimationFrame(animateFrame);
      };
      
      animationRef.current = requestAnimationFrame(animateFrame);
    } else {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
        animationRef.current = undefined;
      }
    }

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
        animationRef.current = undefined;
      }
    };
  }, [isPlaying, frames, frameDuration, onFrameChange, audioManager, audioSettings]);

  // Draw current frame
  useEffect(() => {
    drawFrame(currentFrame);
  }, [currentFrame, drawFrame]);

  // Initialize canvas size
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || frames.length === 0) return;

    const firstFrame = frames[0];
    if (firstFrame) {
      canvas.width = firstFrame.canvas.width;
      canvas.height = firstFrame.canvas.height;
      drawFrame(0);
    }
  }, [frames, drawFrame]);

  const handleFrameSeek = (frameIndex: number) => {
    if (disabled) return;
    setCurrentFrame(frameIndex);
    onFrameChange?.(frameIndex);
  };

  const handleRestart = () => {
    if (disabled) return;
    setCurrentFrame(0);
    onFrameChange?.(0);
  };

  if (frames.length === 0) {
    return (
      <div className={cn("bg-gray-100 rounded-lg flex items-center justify-center", className)}>
        <div className="text-center p-8">
          <div className="w-16 h-16 mx-auto mb-4 bg-gray-300 rounded-lg flex items-center justify-center">
            <Play className="w-8 h-8 text-gray-500" />
          </div>
          <p className="text-gray-600">No frames to preview</p>
          <p className="text-sm text-gray-500 mt-1">
            Upload and align images to see preview
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("bg-white rounded-lg border shadow-sm", className)}>
      {/* Preview Area */}
      <div className="relative bg-gray-900 rounded-t-lg overflow-hidden">
        <canvas
          ref={canvasRef}
          className="w-full h-auto max-h-96 object-contain"
          style={{ 
            maxWidth: '100%',
            height: 'auto',
            display: 'block'
          }}
        />
        
        {/* Loading Overlay */}
        {disabled && (
          <div className="absolute inset-0 bg-black bg-opacity-50 flex items-center justify-center">
            <div className="text-white text-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white mx-auto mb-2"></div>
              <p>Processing frames...</p>
            </div>
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="p-4 space-y-4">
        {/* Playback Controls */}
        <div className="flex items-center justify-center space-x-4">
          <button
            onClick={handleRestart}
            disabled={disabled}
            className="p-2 rounded-full bg-gray-100 hover:bg-gray-200 transition-colors disabled:opacity-50"
            title="Restart"
          >
            <RotateCcw className="w-5 h-5" />
          </button>
          
          <button
            onClick={onPlayPause}
            disabled={disabled}
            className="p-3 rounded-full bg-blue-600 hover:bg-blue-700 text-white transition-colors disabled:opacity-50"
            title={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? (
              <Pause className="w-6 h-6" />
            ) : (
              <Play className="w-6 h-6 ml-1" />
            )}
          </button>
          
          <div className="text-sm text-gray-600">
            {frameDuration}s per frame
          </div>
        </div>

        {/* Frame Scrubber */}
        {frames.length > 1 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm text-gray-600">
              <span>Frame {currentFrame + 1}</span>
              <span>{frames.length} total</span>
            </div>
            
            <div className="relative">
              <input
                type="range"
                min="0"
                max={frames.length - 1}
                value={currentFrame}
                onChange={(e) => handleFrameSeek(parseInt(e.target.value))}
                disabled={disabled}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
              />
              
              {/* Frame Markers */}
              <div className="flex justify-between mt-1">
                {frames.map((_, index) => (
                  <button
                    key={index}
                    onClick={() => handleFrameSeek(index)}
                    disabled={disabled}
                    className={cn(
                      "w-2 h-2 rounded-full transition-colors",
                      {
                        "bg-blue-600": index === currentFrame,
                        "bg-gray-300 hover:bg-gray-400": index !== currentFrame,
                        "opacity-50": disabled,
                      }
                    )}
                    title={`Frame ${index + 1}`}
                  />
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Animation Info */}
        <div className="text-xs text-gray-500 text-center space-y-1">
          <div>
            Duration: {(frames.length * frameDuration).toFixed(1)}s total
          </div>
          <div>
            {frames.length} frames at {(1/frameDuration).toFixed(1)} fps
          </div>
        </div>
      </div>
    </div>
  );
}