# Match Cut Generator - Troubleshooting Guide

## 🔧 Common Issues & Solutions

### 📸 Some Photos Don't Process

**Why this happens:**
- No face detected in the image
- Face is too small, blurry, or at extreme angles
- Poor lighting conditions
- Multiple faces confusing the AI

**Solutions:**
1. ✅ **Use clear, well-lit photos** with visible faces
2. ✅ **Ensure faces are facing forward** (not extreme side profiles)  
3. ✅ **Make sure eyes are clearly visible** (not covered by hair, glasses, etc.)
4. ✅ **Use higher resolution images** when possible
5. ✅ **Try cropping** the image closer to the face before uploading

**What the app does:**
- Automatically detects faces using MediaPipe AI
- Uses fallback detection methods for difficult cases
- Shows helpful status messages when processing fails

### 🎬 Video Export Not Working

**Common causes:**
1. **No internet connection** (required for GIF export)
2. **Browser doesn't support WebCodecs** (older browsers)
3. **FFmpeg failed to load** (network issues)

**Solutions:**
1. ✅ **Check your internet connection** - GIF export requires downloading FFmpeg
2. ✅ **Try MP4 format first** - works offline in modern browsers (Chrome, Edge, Firefox)
3. ✅ **Use a modern browser** - Chrome/Edge have best support
4. ✅ **Try with fewer images** if you have many (reduce memory usage)
5. ✅ **Refresh the page** and try again if initialization failed

**Browser Support:**
- **Best:** Chrome, Edge (full WebCodecs + FFmpeg support)
- **Good:** Firefox (FFmpeg support, limited WebCodecs)
- **Limited:** Safari (FFmpeg only, requires internet)

### 💡 Performance Tips

1. **Image Count:** Start with 5-10 images for best performance (up to 200 images supported)
2. **Image Size:** Resize very large images (>2MB) before uploading  
3. **Browser:** Use Chrome or Edge for best performance
4. **Memory:** Close other browser tabs if experiencing slowness

### 🔍 Debug Information

The app logs detailed information to the browser console:
1. **Open Developer Tools** (F12)
2. **Check Console tab** for detailed error messages
3. **Look for:** Face detection results, export status, error details

### 🆘 Still Having Issues?

**Face Detection Problems:**
- Try different photos with clearer faces
- Ensure good lighting and face visibility
- Check console for specific detection messages

**Export Problems:**  
- Try switching between GIF and MP4 formats
- Check internet connection for GIF export
- Try with fewer images (2-3) to test

**Performance Issues:**
- Reduce image count and size
- Use Chrome/Edge browsers
- Close other applications using memory