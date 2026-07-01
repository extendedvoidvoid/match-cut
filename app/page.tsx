'use client'

import { useState, useCallback, useRef, useEffect } from 'react';
import { Smile, Zap, Download } from 'lucide-react';
import { InstagramIcon } from '@/components/InstagramIcon';
import Link from 'next/link';
import ImageUpload from '@/components/ImageUpload';
import ImageGrid from '@/components/ImageGrid';
import AnimationPreview from '@/components/AnimationPreview';
import ExportOptions from '@/components/ExportOptions';
import ProcessingIndicator from '@/components/ProcessingIndicator';
import { FaceDetector } from '@/lib/faceDetection';
import { ImageAligner } from '@/lib/imageAlignment';
import { VideoExporter } from '@/lib/videoExport';
import { AudioManager } from '@/lib/audioManager';
import { BeatDetector, BeatDetectionResult } from '@/lib/beatDetection';
import { 
  ImageData, 
  ProcessingStatus, 
  ExportSettings, 
  AnimationFrame, 
  VideoExportProgress,
  RESOLUTION_CONFIGS
} from '@/lib/types';
import { generateId, loadImageFromFile, createCanvasFromImage, cn } from '@/lib/utils';

export default function Home() {
  // Core state
  const [images, setImages] = useState<ImageData[]>([]);
  const [processingStatus, setProcessingStatus] = useState<ProcessingStatus>({
    isProcessing: false,
    currentStep: '',
    progress: 0,
  });
  const [exportSettings, setExportSettings] = useState<ExportSettings>({
    format: 'gif',
    resolution: '720p',
    frameDuration: 0.2,
    addSound: false,
    soundType: 'builtin',
    builtinSound: 'click',
    customAudioFile: undefined,
    audioVolume: 0.7,
    beatSync: {
      enabled: false,
      beatSensitivity: 0.5,
      beatOffset: 0,
    },
    loop: true,
    alignmentMode: 'face-crop',
  });
  
  // Animation state
  const [previewFrames, setPreviewFrames] = useState<AnimationFrame[]>([]);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentFrame, setCurrentFrame] = useState(0);
  
  // Export state
  const [isExporting, setIsExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState<VideoExportProgress>();

  // Services
  const faceDetector = useRef<FaceDetector | null>(null);
  const imageAligner = useRef<ImageAligner | null>(null);
  const videoExporter = useRef<VideoExporter | null>(null);
  const audioManager = useRef<AudioManager | null>(null);
  const beatDetector = useRef<BeatDetector | null>(null);
  const [servicesReady, setServicesReady] = useState(false);
  
  // Beat sync state
  const [beatDetectionResult, setBeatDetectionResult] = useState<BeatDetectionResult | null>(null);
  const [isAnalyzingBeats, setIsAnalyzingBeats] = useState(false);

  // Initialize services
  useEffect(() => {
    const initializeServices = async () => {
      try {
        // Migrate existing images to have status property
        setImages(prev => prev.map(img => ({
          ...img,
          status: img.status || (img.aligned ? 'aligned' as const : 'pending' as const)
        })));

        setProcessingStatus({
          isProcessing: true,
          currentStep: 'Initializing AI services...',
          progress: 0,
        });

        // Initialize MediaPipe face detector
        faceDetector.current = new FaceDetector();
        await faceDetector.current.initialize();
        
        setProcessingStatus(prev => ({ ...prev, progress: 0.33 }));

        // Initialize image aligner
        imageAligner.current = new ImageAligner();
        
        setProcessingStatus(prev => ({ ...prev, progress: 0.66 }));

        // Initialize video exporter
        videoExporter.current = new VideoExporter();
        await videoExporter.current.initialize();
        
        setProcessingStatus(prev => ({ ...prev, progress: 0.8 }));

        // Initialize audio manager
        audioManager.current = new AudioManager();
        
        setProcessingStatus(prev => ({ ...prev, progress: 0.9 }));

        // Initialize beat detector
        beatDetector.current = new BeatDetector();
        
        setProcessingStatus({
          isProcessing: false,
          currentStep: 'Ready',
          progress: 1,
        });

        setServicesReady(true);
        console.log('All services initialized successfully');
      } catch (error) {
        console.error('Failed to initialize services:', error);
        setProcessingStatus({
          isProcessing: false,
          currentStep: 'Initialization failed',
          progress: 0,
          error: 'Failed to initialize AI services. Please refresh the page.',
        });
      }
    };

    initializeServices();

    return () => {
      faceDetector.current?.cleanup();
      videoExporter.current?.cleanup();
      audioManager.current?.cleanup();
      beatDetector.current?.cleanup();
    };
  }, []);

  // Load audio when settings change
  useEffect(() => {
    if (!audioManager.current) return;

    const loadAudio = async () => {
      try {
        if (exportSettings.addSound && exportSettings.soundType === 'builtin') {
          console.log(`Loading built-in sound: ${exportSettings.builtinSound}`);
          await audioManager.current!.loadBuiltinSound(exportSettings.builtinSound);
        } else if (exportSettings.addSound && exportSettings.soundType === 'custom' && exportSettings.customAudioFile) {
          console.log(`Loading custom sound: ${exportSettings.customAudioFile.name}`);
          await audioManager.current!.loadCustomSound(exportSettings.customAudioFile);
        }
      } catch (error) {
        console.error('Failed to load audio:', error);
      }
    };

    loadAudio();
  }, [exportSettings.addSound, exportSettings.soundType, exportSettings.builtinSound, exportSettings.customAudioFile]);

  // Analyze beats when music file changes
  useEffect(() => {
    if (!beatDetector.current || !exportSettings.beatSync.enabled || !exportSettings.beatSync.musicFile) {
      setBeatDetectionResult(null);
      return;
    }

    const analyzeBeats = async () => {
      setIsAnalyzingBeats(true);
      try {
        const audioBuffer = await beatDetector.current!.loadAudioFile(exportSettings.beatSync.musicFile!);
        
        // SMART DETECTION: Let algorithm detect natural beats, don't force image count
        const alignedImages = images.filter(img => img.status === 'aligned');
        
        console.log(`🎯 Smart beat detection: ${alignedImages.length} images available`);
        console.log(`   Algorithm will detect natural beats, then use min(images, beats)`);
        
        // Don't pass targetBeatCount - let it detect naturally
        const result = await beatDetector.current!.detectBeats(
          audioBuffer, 
          exportSettings.beatSync.beatSensitivity,
          undefined  // Let algorithm find all natural beats
        );
        setBeatDetectionResult(result);
        console.log('Beat detection result:', result);
      } catch (error) {
        console.error('Beat detection failed:', error);
        setBeatDetectionResult(null);
      } finally {
        setIsAnalyzingBeats(false);
      }
    };

    analyzeBeats();
  }, [exportSettings.beatSync.enabled, exportSettings.beatSync.musicFile, exportSettings.beatSync.beatSensitivity, images]);

  // Handle image upload
  const handleImagesUpload = useCallback(async (files: File[]) => {
    if (!servicesReady) return;

    const newImages: ImageData[] = files.map(file => ({
      id: generateId(),
      file,
      url: URL.createObjectURL(file),
      aligned: false,
      status: 'pending' as const,
    }));

    setImages(prev => [...prev, ...newImages]);

    // Process images automatically
    await processImages([...images, ...newImages]);
  }, [servicesReady, images]);

  // Process images with face detection and alignment
  const processImages = useCallback(async (imagesToProcess: ImageData[]) => {
    if (!faceDetector.current || !imageAligner.current) return;

    const unalignedImages = imagesToProcess.filter(img => img.status === 'pending' || img.status === 'failed');
    if (unalignedImages.length === 0) return;

    // Reset smoothing state for new batch of images
    imageAligner.current.resetSmoothingState();

    setProcessingStatus({
      isProcessing: true,
      currentStep: 'Detecting faces and aligning images...',
      progress: 0,
    });

    const resolution = RESOLUTION_CONFIGS[exportSettings.resolution];
    const processedImages: ImageData[] = [];

    // First, mark all images as processing
    setImages(prev => prev.map(img => 
      unalignedImages.some(u => u.id === img.id) 
        ? { ...img, status: 'processing' as const }
        : img
    ));

    for (let i = 0; i < unalignedImages.length; i++) {
      const image = unalignedImages[i];
      
      try {
        setProcessingStatus(prev => ({
          ...prev,
          currentStep: `Processing ${image.file.name}...`,
          progress: i / unalignedImages.length,
        }));

        // Load image
        const imgElement = await loadImageFromFile(image.file);
        
        // Detect face and eyes
        const faceResult = await faceDetector.current.detectFace(imgElement);
        
        if (!faceResult || !faceResult.eyePoints) {
          console.warn(`No face detected in ${image.file.name}`);
          // Show more helpful message to user
          setProcessingStatus(prev => ({
            ...prev,
            currentStep: `No face found in ${image.file.name} - marked as failed`,
          }));
          processedImages.push({
            ...image,
            aligned: false,
            status: 'failed' as const,
            error: 'No face detected in this image. Please ensure the image contains a clear, front-facing face.',
          });
          continue;
        }

        // Validate eye points
        if (!imageAligner.current.validateEyePoints(
          faceResult.eyePoints, 
          imgElement.width, 
          imgElement.height
        )) {
          console.warn(`Invalid eye points in ${image.file.name}`);
          processedImages.push({
            ...image,
            aligned: false,
            status: 'failed' as const,
            error: 'Face detected but eye points are invalid. Try with a clearer image with visible eyes.',
          });
          continue;
        }

        // Align image using selected alignment mode
        let alignedCanvas: HTMLCanvasElement;
        if (exportSettings.alignmentMode === 'face-crop') {
          alignedCanvas = imageAligner.current.alignImageFaceCrop(
            imgElement,
            faceResult,
            resolution
          );
        } else {
          // Default to full alignment
          alignedCanvas = imageAligner.current.alignImageFull(
            imgElement,
            faceResult.eyePoints,
            resolution
          );
        }

        // Create processed URL
        const processedUrl = await new Promise<string>((resolve) => {
          alignedCanvas.toBlob((blob) => {
            if (blob) {
              resolve(URL.createObjectURL(blob));
            }
          }, 'image/png');
        });

        processedImages.push({
          ...image,
          aligned: true,
          status: 'aligned' as const,
          eyePoints: faceResult.eyePoints,
          faceResult: faceResult,
          alignedCanvas,
          processedUrl,
          error: undefined, // Clear any previous errors
        });

      } catch (error) {
        console.error(`Failed to process ${image.file.name}:`, error);
        processedImages.push({
          ...image,
          aligned: false,
          status: 'failed' as const,
          error: `Processing failed: ${error instanceof Error ? error.message : 'Unknown error'}`,
        });
      }
    }

    // Update images state
    setImages(prev => {
      const updated = [...prev];
      processedImages.forEach(processedImg => {
        const index = updated.findIndex(img => img.id === processedImg.id);
        if (index !== -1) {
          updated[index] = processedImg;
        }
      });
      return updated;
    });

    // Generate preview frames
    await generatePreviewFrames(imagesToProcess.map(img => {
      const processed = processedImages.find(p => p.id === img.id);
      return processed || img;
    }).filter(img => img.status === 'aligned'));

    setProcessingStatus({
      isProcessing: false,
      currentStep: `Processing complete - ${processedImages.filter(p => p.status === 'aligned').length} of ${processedImages.length} images aligned`,
      progress: 1,
    });
  }, [exportSettings.resolution, exportSettings.alignmentMode]);

  // Generate preview frames
  const generatePreviewFrames = useCallback(async (alignedImages: ImageData[]) => {
    if (alignedImages.length === 0) {
      setPreviewFrames([]);
      return;
    }

    console.log('Generating preview frames for', alignedImages.length, 'images');
    
    // Calculate frame durations ONCE before mapping
    let frameDurations: number[];
    let imagesToUse = alignedImages;
    
    if (exportSettings.beatSync.enabled && beatDetectionResult && beatDetector.current) {
      // BEAT SYNC MODE: Use detected beats to calculate durations
      frameDurations = beatDetector.current.generateFrameDurations(
        beatDetectionResult.beats,
        alignedImages.length,
        exportSettings.beatSync.beatOffset
      );
      
      // TRUNCATE images to match beat count
      if (frameDurations.length < alignedImages.length) {
        imagesToUse = alignedImages.slice(0, frameDurations.length);
        console.warn(`⚠️ Truncated ${alignedImages.length} images to ${frameDurations.length} (matching detected beats)`);
      }
      
      console.log('🎵 Beat Sync Enabled:', {
        detectedBeats: beatDetectionResult.beats.length,
        bpm: beatDetectionResult.bpm,
        totalImages: alignedImages.length,
        usedImages: imagesToUse.length,
        offset: exportSettings.beatSync.beatOffset,
        frameDurations: frameDurations
      });
    } else {
      // NORMAL MODE: Use fixed frame duration
      frameDurations = Array(alignedImages.length).fill(exportSettings.frameDuration);
      console.log('⏱️ Normal Mode:', {
        frameDuration: exportSettings.frameDuration,
        imageCount: alignedImages.length
      });
    }
    
    const frames: AnimationFrame[] = imagesToUse.map((image, index) => {
      const canvas = image.alignedCanvas!;
      
      // Debug: Check if each canvas has content
      const ctx = canvas.getContext('2d')!;
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const hasContent = imageData.data.some((value, index) => {
        return index % 4 === 3 && value > 0; // Check alpha channel for non-transparent pixels
      });
      
      console.log(`Frame ${index + 1}:`, {
        canvasSize: { width: canvas.width, height: canvas.height },
        hasContent,
        duration: frameDurations[index] || exportSettings.frameDuration,
        imageId: image.id
      });
      
      if (!hasContent) {
        console.warn(`WARNING: Frame ${index + 1} (${image.id}) appears to be empty!`);
      }
      
      return {
        canvas,
        duration: frameDurations[index] || exportSettings.frameDuration, // Fallback to default
        imageId: image.id,
      };
    });

    console.log('Generated', frames.length, 'frames for preview');
    setPreviewFrames(frames);
  }, [exportSettings.frameDuration, exportSettings.beatSync, beatDetectionResult]);

  // Handle image removal
  const handleRemoveImage = useCallback((id: string) => {
    setImages(prev => {
      const filtered = prev.filter(img => img.id !== id);
      // Update preview frames
      generatePreviewFrames(filtered.filter(img => img.status === 'aligned'));
      return filtered;
    });
  }, [generatePreviewFrames]);

  // Handle image reordering
  const handleReorderImages = useCallback((fromIndex: number, toIndex: number) => {
    setImages(prev => {
      const newImages = [...prev];
      const [moved] = newImages.splice(fromIndex, 1);
      newImages.splice(toIndex, 0, moved);
      
      // Update preview frames
      generatePreviewFrames(newImages.filter(img => img.status === 'aligned'));
      return newImages;
    });
  }, [generatePreviewFrames]);

  // Handle retry alignment
  const handleRetryAlignment = useCallback(async (id: string) => {
    const imageToRetry = images.find(img => img.id === id);
    if (!imageToRetry) return;

    await processImages([imageToRetry]);
  }, [images]);

  // Handle export
  const handleExport = useCallback(async () => {
    if (!videoExporter.current || previewFrames.length === 0) {
      alert('No frames available for export. Please ensure images are processed and aligned.');
      return;
    }

    console.log('Starting export...');
    setIsExporting(true);
    setExportProgress({ phase: 'preparing', progress: 0 });

    try {
      const resolution = RESOLUTION_CONFIGS[exportSettings.resolution];
      
      console.log('Export configuration:', {
        frames: previewFrames.length,
        settings: exportSettings,
        resolution
      });
      
      try {
        await videoExporter.current.exportAndDownload(
          previewFrames,
          exportSettings,
          resolution,
          `match-cut-${Date.now()}`,
          setExportProgress,
          audioManager.current || undefined
        );

        console.log('Export completed successfully');
      } catch (error) {
        console.error('Export failed:', error);
        const errorMessage = error instanceof Error ? error.message : 'Unknown export error';
        alert(`Export failed: ${errorMessage}\n\nTips:\n- Try a different format (GIF vs MP4)\n- Check your internet connection\n- Try with fewer images`);
      }
    } catch (error) {
      console.error('Export failed:', error);
      const errorMessage = error instanceof Error ? error.message : 'Unknown export error';
      alert(`Export failed: ${errorMessage}\n\nTips:\n- Try a different format (GIF vs MP4)\n- Check your internet connection\n- Try with fewer images`);
    } finally {
      setIsExporting(false);
      setExportProgress(undefined);
    }
  }, [previewFrames, exportSettings]);

  // Update preview frames when settings change
  useEffect(() => {
    const alignedImages = images.filter(img => img.status === 'aligned');
    generatePreviewFrames(alignedImages);
  }, [images, generatePreviewFrames]);

  // Reprocess images when alignment mode changes
  useEffect(() => {
    const alignedImages = images.filter(img => img.status === 'aligned' && img.faceResult);
    if (alignedImages.length > 0) {
      // Re-align existing images with new mode
      alignedImages.forEach(async (image) => {
        if (image.faceResult && imageAligner.current) {
          const resolution = RESOLUTION_CONFIGS[exportSettings.resolution];
          
          let alignedCanvas: HTMLCanvasElement;
          if (exportSettings.alignmentMode === 'face-crop') {
            alignedCanvas = imageAligner.current.alignImageFaceCrop(
              await loadImageFromFile(image.file),
              image.faceResult,
              resolution
            );
          } else {
            alignedCanvas = imageAligner.current.alignImageFull(
              await loadImageFromFile(image.file),
              image.faceResult.eyePoints,
              resolution
            );
          }
          
          // Update processed URL
          const processedUrl = await new Promise<string>((resolve) => {
            alignedCanvas.toBlob((blob) => {
              if (blob) {
                resolve(URL.createObjectURL(blob));
              }
            }, 'image/png');
          });
          
          // Update image data
          setImages(prev => prev.map(img => 
            img.id === image.id 
              ? { ...img, alignedCanvas, processedUrl }
              : img
          ));
        }
      });
    }
  }, [exportSettings.alignmentMode, exportSettings.resolution]);

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 bg-yellow-400 rounded-lg flex items-center justify-center">
                <Smile className="w-5 h-5 text-gray-900" />
              </div>
              <h1 className="text-xl font-bold text-gray-900">
                Match Cut Generator
              </h1>
            </div>
            
            <div className="flex items-center space-x-4">
              <Link
                href="/about"
                className="text-gray-600 hover:text-gray-900 px-3 py-2 rounded-md hover:bg-gray-100"
                target={processingStatus.isProcessing ? '_blank' : undefined}
                rel={processingStatus.isProcessing ? 'noopener noreferrer' : undefined}
              >
                About
              </Link>
              <a 
                href="https://www.producthunt.com/products/face-match-cut-generator?embed=true&utm_source=badge-featured&utm_medium=badge&utm_source=badge-face&#0045;match&#0045;cut&#0045;generator" 
                target="_blank"
                className="hover:opacity-80 transition-opacity"
              >
                <img 
                  src="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1015749&theme=light&t=1757742596193" 
                  alt="Face Match Cut Generator - Upload Photos, Generate Eye-Aligned Animations in Seconds | Product Hunt" 
                  style={{ width: '250px', height: '54px' }} 
                  width="250" 
                  height="54" 
                />
              </a>
              
              <a
                href="https://www.instagram.com/sanjogsays/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-gray-500 hover:text-gray-700 transition-colors"
              >
                <InstagramIcon className="w-5 h-5" />
              </a>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Hero Section */}
        {images.length === 0 && !processingStatus.isProcessing && (
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">
              Create Eye-Aligned Match Cut Videos
            </h2>
            <p className="text-lg text-gray-600 max-w-2xl mx-auto">
              Upload multiple photos and automatically generate smooth match cut animations 
              with perfect eye alignment. Export as GIF or MP4 with customizable settings.
            </p>
          </div>
        )}

        {/* Processing Indicator */}
        {(processingStatus.isProcessing || processingStatus.error) && (
          <div className="mb-8">
            <ProcessingIndicator status={processingStatus} />
          </div>
        )}

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left Column - Upload & Images */}
          <div className="lg:col-span-2 space-y-8">
            {/* Image Upload */}
            <div className="card p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">
                Upload Images
              </h3>
              <ImageUpload
                onImagesUpload={handleImagesUpload}
                disabled={!servicesReady || processingStatus.isProcessing}
              />
            </div>

            {/* Alignment Mode - Only show when images are uploaded */}
            {images.length > 0 && (
              <div className="card p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">
                  Alignment Mode
                </h3>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    onClick={() => setExportSettings(prev => ({ ...prev, alignmentMode: 'face-crop' }))}
                    disabled={!servicesReady || processingStatus.isProcessing}
                    className={cn(
                      "p-4 border-2 rounded-lg text-left transition-all",
                      "hover:border-blue-300 disabled:opacity-50",
                      {
                        "border-blue-500 bg-blue-50": exportSettings.alignmentMode === 'face-crop',
                        "border-gray-200": exportSettings.alignmentMode !== 'face-crop',
                      }
                    )}
                  >
                    <div className="font-medium">Smart Crop (Recommended)</div>
                    <div className="text-sm text-gray-500 mt-1">
                      Focus on face region with perfect eye alignment
                    </div>
                  </button>
                  
                  <button
                    onClick={() => setExportSettings(prev => ({ ...prev, alignmentMode: 'full' }))}
                    disabled={!servicesReady || processingStatus.isProcessing}
                    className={cn(
                      "p-4 border-2 rounded-lg text-left transition-all",
                      "hover:border-blue-300 disabled:opacity-50",
                      {
                        "border-blue-500 bg-blue-50": exportSettings.alignmentMode === 'full',
                        "border-gray-200": exportSettings.alignmentMode !== 'full',
                      }
                    )}
                  >
                    <div className="font-medium">Full Image</div>
                    <div className="text-sm text-gray-500 mt-1">
                      Show entire photo with eye alignment
                    </div>
                  </button>
                </div>
              </div>
            )}

            {/* Image Grid */}
            {images.length > 0 && (
              <div className="card p-6">
                <ImageGrid
                  images={images}
                  onRemoveImage={handleRemoveImage}
                  onReorderImages={handleReorderImages}
                  onRetryAlignment={handleRetryAlignment}
                  disabled={!servicesReady || processingStatus.isProcessing}
                />
              </div>
            )}
          </div>

          {/* Right Column - Preview & Export */}
          <div className="space-y-8">
            {/* Animation Preview */}
            <div className="card p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">
                Preview
              </h3>
              <AnimationPreview
                frames={previewFrames}
                frameDuration={exportSettings.frameDuration}
                isPlaying={isPlaying}
                onPlayPause={() => setIsPlaying(!isPlaying)}
                onFrameChange={setCurrentFrame}
                audioSettings={exportSettings}
                audioManager={audioManager.current}
                disabled={processingStatus.isProcessing}
              />
            </div>

            {/* Export Options */}
            <ExportOptions
              settings={exportSettings}
              onSettingsChange={setExportSettings}
              onExport={handleExport}
              isExporting={isExporting}
              exportProgress={exportProgress}
              audioManager={audioManager.current}
              disabled={!servicesReady || previewFrames.length === 0}
            />
          </div>
        </div>

        {/* Stats & Info */}
        {images.length > 0 && (
          <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="card p-6 text-center">
              <div className="text-3xl font-bold text-blue-600 mb-2">
                {images.length}
              </div>
              <div className="text-gray-600">Images Uploaded</div>
            </div>
            
            <div className="card p-6 text-center">
              <div className="text-3xl font-bold text-green-600 mb-2">
                {images.filter(img => img.status === 'aligned').length}
              </div>
              <div className="text-gray-600">Successfully Aligned</div>
            </div>
            
            <div className="card p-6 text-center">
              <div className="text-3xl font-bold text-purple-600 mb-2">
                {previewFrames.length > 0 ? (previewFrames.length * exportSettings.frameDuration).toFixed(1) : '0'}s
              </div>
              <div className="text-gray-600">Animation Duration</div>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="bg-gray-50 border-t mt-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center text-gray-600">
            <p className="mb-2">
              Built with MediaPipe, FFmpeg.wasm, and React
            </p>
            <p className="text-sm">
              All processing happens in your browser - your images never leave your device
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}