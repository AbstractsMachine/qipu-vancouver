import type { Compositor, DrawPass, DrawSource } from "./compositor";

/* A port of `eras/switch.ts` (decodeSwitchPixel, progress, pixelWeights): keep the two in step. */
const VERTEX = `
attribute vec2 p;
varying vec2 v;
void main() { v = p; gl_Position = vec4(p.x * 2.0 - 1.0, 1.0 - p.y * 2.0, 0.0, 1.0); }`;

const FRAGMENT = `
precision highp float;
varying vec2 v;
uniform sampler2D uFrom, uTo, uClear, uSwitch;
uniform vec3 wFrom, wTo, wClear, wSwitch;
uniform float hasFrom, hasTo, hasClear, hasSwitch;
uniform float uT, uMid, uScale, uLeadStep, uEncoding;

vec4 tex(sampler2D s, vec3 w, float has) { return has > 0.5 ? texture2D(s, w.xy + v * w.z) : vec4(0.0); }
float progress(float t, float d, float w) { return w > 0.0 ? smoothstep(0.4, 0.6, clamp((t - d) / w, 0.0, 1.0)) : step(d, t); }

void main() {
  vec4 a = tex(uFrom, wFrom, hasFrom);
  vec4 b = tex(uTo, wTo, hasTo);
  float d = uMid;
  float w = 0.0;
  float lead = 0.0;
  if (hasSwitch > 0.5) {
    vec3 c = texture2D(uSwitch, wSwitch.xy + v * wSwitch.z).rgb;
    float code = floor(c.r * 255.0 + 0.5) * 256.0 + floor(c.g * 255.0 + 0.5);
    d = code > 65534.5 ? 1.0e9 : (code < 0.5 && uEncoding < 2.5 ? uMid : code);
    float blue = floor(c.b * 255.0 + 0.5);
    if (uEncoding > 2.5) {
      w = 0.0;
    } else if (uEncoding < 0.5) {
      w = blue * 0.005 * uScale;
    } else {
      float fade = mod(blue, 16.0);
      w = fade > 0.5 ? 0.0015 * exp2(fade - 1.0) * uScale : 0.0;
      if (uEncoding > 1.5) lead = floor(blue / 16.0) * uLeadStep * uScale;
    }
  }
  vec4 site = a;
  if (lead > 0.0 && hasClear > 0.5) {
    vec4 cleared = texture2D(uClear, wClear.xy + v * wClear.z);
    if (cleared.a > 0.5) site = cleared;
  }
  vec4 before = lead > 0.0 ? mix(a, site, progress(uT, d - lead, w)) : a;
  gl_FragColor = mix(before, b, progress(uT, d, w));
}`;

const SLOTS = ["From", "To", "Clear", "Switch"] as const;
const ENCODINGS = { c3: 0, c3c: 1, c3d: 2, q1: 3 } as const;

export function createGlCompositor(size: number): Compositor | null {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const gl = canvas.getContext("webgl", { premultipliedAlpha: true, alpha: true, antialias: false });
  if (!gl) return null;
  const program = link(gl);
  if (!program) return null;

  let ok = true;
  canvas.addEventListener("webglcontextlost", (e) => {
    e.preventDefault();
    ok = false;
  });

  const quad = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, quad);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]), gl.STATIC_DRAW);
  const attr = gl.getAttribLocation(program, "p");
  gl.enableVertexAttribArray(attr);
  gl.vertexAttribPointer(attr, 2, gl.FLOAT, false, 0, 0);
  gl.useProgram(program);
  const locations = new Map<string, WebGLUniformLocation | null>();
  const u = (name: string) => {
    if (!locations.has(name)) locations.set(name, gl.getUniformLocation(program, name));
    return locations.get(name) ?? null;
  };
  SLOTS.forEach((slot, i) => {
    gl.uniform1i(u(`u${slot}`), i);
  });
  gl.viewport(0, 0, size, size);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
  gl.clearColor(0, 0, 0, 0);

  const textures = new Map<ImageBitmap, WebGLTexture>();
  const textureOf = (image: ImageBitmap, nearest: boolean): WebGLTexture | null => {
    const hit = textures.get(image);
    if (hit) return hit;
    const t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    const filter = nearest ? gl.NEAREST : gl.LINEAR;
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
    textures.set(image, t);
    return t;
  };

  const bind = (slot: number, name: (typeof SLOTS)[number], src: DrawSource | null, nearest: boolean) => {
    gl.activeTexture(gl.TEXTURE0 + slot);
    const has = !!src?.image;
    gl.bindTexture(gl.TEXTURE_2D, src?.image ? textureOf(src.image, nearest) : null);
    gl.uniform1f(u(`has${name}`), has ? 1 : 0);
    const w = src?.window ?? [0, 0, 1];
    gl.uniform3f(u(`w${name}`), w[0], w[1], w[2]);
  };

  const drawPass = (p: DrawPass) => {
    bind(0, "From", p.from, false);
    bind(1, "To", p.to, false);
    bind(2, "Clear", p.clear, false);
    bind(3, "Switch", p.switchMap, true);
    gl.uniform1f(u("uT"), p.t);
    gl.uniform1f(u("uMid"), p.mid);
    gl.uniform1f(u("uScale"), p.sw.scale);
    gl.uniform1f(u("uLeadStep"), p.sw.leadStep);
    gl.uniform1f(u("uEncoding"), ENCODINGS[p.sw.encoding]);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  };

  return {
    kind: "webgl",
    get ok() {
      return ok && !gl.isContextLost();
    },
    draw(target, passes) {
      gl.clear(gl.COLOR_BUFFER_BIT);
      for (const p of passes) drawPass(p);
      const ctx = target.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, target.width, target.height);
      ctx.drawImage(canvas, 0, 0, target.width, target.height);
    },
    forget(bitmap) {
      const t = textures.get(bitmap);
      if (t) gl.deleteTexture(t);
      textures.delete(bitmap);
    },
    dispose() {
      for (const t of textures.values()) gl.deleteTexture(t);
      textures.clear();
      gl.getExtension("WEBGL_lose_context")?.loseContext();
    },
  };
}

function link(gl: WebGLRenderingContext): WebGLProgram | null {
  const compile = (type: number, source: string) => {
    const s = gl.createShader(type);
    if (!s) return null;
    gl.shaderSource(s, source);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.error("era shader:", gl.getShaderInfoLog(s));
      return null;
    }
    return s;
  };
  const vs = compile(gl.VERTEX_SHADER, VERTEX);
  const fs = compile(gl.FRAGMENT_SHADER, FRAGMENT);
  const program = gl.createProgram();
  if (!vs || !fs) return null;
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    console.error("era shader:", gl.getProgramInfoLog(program));
    return null;
  }
  return program;
}
