let scratch: HTMLCanvasElement | null = null;

/** An image's pixels as stored (no smoothing), or null where the browser has no 2D canvas. */
export function readPixels(image: ImageBitmap): Uint8ClampedArray | null {
  scratch ??= document.createElement("canvas");
  scratch.width = image.width;
  scratch.height = image.height;
  const ctx = scratch.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  ctx.clearRect(0, 0, image.width, image.height);
  ctx.drawImage(image, 0, 0);
  return ctx.getImageData(0, 0, image.width, image.height).data;
}
