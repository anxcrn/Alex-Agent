---
name: website-3d-motion
description: "A comprehensive guide to building responsive, highly-optimized websites with 3D motions using Three.js and React Three Fiber (R3F)."
version: 1.0.0
author: Alex Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  alex:
    tags: [web-development, 3d, threejs, react-three-fiber, webgl, canvas, animation]
    related_skills: [fullstack-developer, plan]
---

# Building Websites with 3D Motion (Three.js & React Three Fiber)

## Overview

Integrating 3D motion into websites creates an immersive, premium user experience. This skill provides a structured methodology to build, optimize, and deploy web applications containing 3D elements, animations, and interactive scenes.

We focus on two major approaches:
1. **React Three Fiber (R3F)**: Declarative, component-based 3D inside React. Highly recommended for modern React/Next.js/Vite applications.
2. **Vanilla Three.js**: Imperative, library-agnostic 3D. Best for lightweight, single-page, or framework-free deployments.

---

## When to Use

Use this skill when:
- Designing **interactive landing pages** or portfolios that require visual impact.
- Building **3D product configurators** or viewers.
- Implementing **scrolling animations** where 3D elements react to user scroll depth (scroll-linked animations).
- Creating **dynamic background environments** (particles, abstract geometries, or interactive shaders).

Do NOT use this skill when:
- The website is purely text/data-heavy and performance/load-time is the absolute highest priority.
- Target users are primarily on low-end legacy mobile devices with no WebGL support.
- Static 2D images or standard CSS/Lottie animations can achieve the same UX goal with 90% less complexity.

---

## Prerequisites

To implement 3D web features, you need:
- **Node.js** (v18.0.0 or higher) and **npm** / **yarn** / **pnpm**.
- A standard bundler setup (e.g., **Vite** or **Next.js**).
- Basic understanding of:
  - 3D Coordinates (X, Y, Z space).
  - Cameras (Perspective vs. Orthographic).
  - Lighting (Ambient, Directional, Point, Spot).
  - Materials (MeshBasicMaterial, MeshStandardMaterial, MeshPhysicalMaterial).
  - Render Loop (`requestAnimationFrame`).

### Core Libraries to Install

#### For React Projects (R3F Stack):
```bash
npm install three @types/three @react-three/fiber @react-three/drei gsap
```

#### For Vanilla JS Projects:
```bash
npm install three @types/three gsap
```

---

## How to Run

1. Open your project root directory.
2. Review this skill file to understand the integration pattern.
3. Use the **Procedure** below to scaffold a Canvas container, add your scene, camera, lights, mesh, and set up the animation loop.
4. Run your local dev server (e.g., `npm run dev`) and verify WebGL rendering.

---

## Procedure

### Phase 1: Set Up the 3D Canvas Context

Every WebGL/3D scene needs a canvas container.

#### Option A: React Three Fiber (Recommended)

In R3F, `<Canvas>` sets up the WebGLRenderer, Scene, and Camera automatically.

```tsx
// src/components/Scene3D.tsx
import React, { useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Center } from "@react-three/drei";
import * as THREE from "three";

function SpinningBox() {
  const meshRef = useRef<THREE.Mesh>(null);

  // useFrame hooks into the render loop (requestAnimationFrame)
  useFrame((state, delta) => {
    if (meshRef.current) {
      meshRef.current.rotation.x += delta * 0.5;
      meshRef.current.rotation.y += delta * 0.8;
    }
  });

  return (
    <mesh ref={meshRef} position={[0, 0, 0]}>
      <boxGeometry args={[1.5, 1.5, 1.5]} />
      <meshStandardMaterial color="#3b82f6" roughness={0.1} metalness={0.8} />
    </mesh>
  );
}

export default function Scene3D() {
  return (
    <div className="w-full h-[500px] bg-slate-950 rounded-xl overflow-hidden relative">
      <Canvas camera={{ position: [3, 3, 3], fov: 45 }}>
        {/* Lights */}
        <ambientLight intensity={0.5} />
        <directionalLight position={[5, 5, 5]} intensity={1.5} castShadow />
        <pointLight position={[-5, -5, -5]} intensity={0.5} />

        {/* 3D Elements */}
        <Center>
          <SpinningBox />
        </Center>

        {/* Controls */}
        <OrbitControls enableZoom={false} makeDefault />
      </Canvas>
    </div>
  );
}
```

#### Option B: Vanilla Three.js Setup

For vanilla JS, you must instantiate the Scene, Camera, Renderer, and Render Loop manually.

```typescript
// src/three-scene.ts
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export function initThreeScene(container: HTMLDivElement) {
  // 1. Create Scene
  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#020617");

  // 2. Create Camera
  const camera = new THREE.PerspectiveCamera(
    45,
    container.clientWidth / container.clientHeight,
    0.1,
    100
  );
  camera.position.set(3, 3, 3);

  // 3. Create Renderer
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  container.appendChild(renderer.domElement);

  // 4. Add Lights
  const ambientLight = new THREE.AmbientLight("#ffffff", 0.5);
  scene.add(ambientLight);

  const dirLight = new THREE.DirectionalLight("#ffffff", 1.5);
  dirLight.position.set(5, 5, 5);
  dirLight.castShadow = true;
  scene.add(dirLight);

  // 5. Add Object
  const geometry = new THREE.BoxGeometry(1.5, 1.5, 1.5);
  const material = new THREE.MeshStandardMaterial({
    color: "#3b82f6",
    roughness: 0.1,
    metalness: 0.8,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  scene.add(mesh);

  // 6. Add Orbit Controls
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableZoom = false;

  // 7. Handle Resize
  const handleResize = () => {
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
  };
  window.addEventListener("resize", handleResize);

  // 8. Animation Loop
  const clock = new THREE.Clock();
  let animationId: number;

  const tick = () => {
    const elapsedTime = clock.getElapsedTime();

    // Rotate mesh
    mesh.rotation.x = elapsedTime * 0.5;
    mesh.rotation.y = elapsedTime * 0.8;

    // Render
    controls.update();
    renderer.render(scene, camera);

    // Call tick again on next frame
    animationId = requestAnimationFrame(tick);
  };

  tick();

  // Cleanup helper
  return () => {
    window.removeEventListener("resize", handleResize);
    cancelAnimationFrame(animationId);
    renderer.dispose();
    geometry.dispose();
    material.dispose();
    container.removeChild(renderer.domElement);
  };
}
```

---

### Phase 2: Advanced Animations (Scroll-linked Motion)

For websites, tying 3D elements to scroll position (using GSAP or Framer Motion) creates beautiful, premium landing pages.

#### scroll-linked 3D mesh with GSAP:

```typescript
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import * as THREE from "three";

gsap.registerPlugin(ScrollTrigger);

export function setupScrollAnimation(mesh: THREE.Mesh) {
  gsap.to(mesh.rotation, {
    x: Math.PI * 2,
    y: Math.PI * 1.5,
    scrollTrigger: {
      trigger: ".scroll-trigger-section", // HTML trigger container
      start: "top top",
      end: "bottom bottom",
      scrub: 1, // Smooth scrub interaction
    },
  });

  gsap.to(mesh.position, {
    x: 2, // Move mesh to the side to make space for text
    z: -1,
    scrollTrigger: {
      trigger: ".scroll-trigger-section",
      start: "top top",
      end: "bottom bottom",
      scrub: 1,
    },
  });
}
```

---

### Phase 3: WebGL Optimization Best Practices

WebGL runs on client GPUs. Poorly optimized scenes cause lag, battery drain, and thermal throttling.

1. **Geometry Reuse**: Reuse `BufferGeometry` instances for identical meshes. Do not create new geometries in loops.
2. **Texture Sizes**: Always use power-of-two (POT) texture resolutions (e.g., 512x512, 1024x1024, 2024x2024). Keep file sizes small using compression (e.g., `.webp` or compressed `.basis`/`.ktx2` formats).
3. **Limit Draw Calls**: Merge geometries when rendering thousands of static objects (use `THREE.InstancedMesh` or merge buffers).
4. **Reduce Shadow Maps**: Shadows are extremely expensive. Use low resolution shadow maps (e.g., `512` or `1024`), turn off shadows for tiny/distant objects, or use baked lighting.
5. **Pixel Ratio Limit**: Limit the renderer pixel ratio to a maximum of `2` (Retina/High-DPI screens look sharp enough at 2x, rendering at 3x or 4x is wasteful and lags).
   - R3F: `<Canvas dpr={[1, 2]}>`
   - Vanilla: `renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))`

---

## Quick Reference

| Feature | R3F Component | Vanilla Equivalent |
|---|---|---|
| **Scene Box** | `<mesh>` | `new THREE.Mesh(geometry, material)` |
| **Orbit Controls** | `<OrbitControls />` | `new OrbitControls(camera, domElement)` |
| **AnimationFrame** | `useFrame((state, delta) => {})` | `requestAnimationFrame(tick)` |
| **GLTF Model Loader** | `useGLTF('/model.gltf')` | `new GLTFLoader().load(...)` |
| **Instanced Rendering**| `<instancedMesh>` | `new THREE.InstancedMesh(...)` |

---

## Pitfalls & Troubleshooting

### 1. Canvas Dimensions are 0px (Black Screen)
- **Symptom**: Canvas is loaded in DOM but black, or has width/height of 0px.
- **Fix**: The Canvas wrapper element must have explicit width and height in CSS. For Tailwind, use `w-full h-screen` or `h-[500px]`. For CSS: `.canvas-container { width: 100%; height: 500px; position: relative; }`.

### 2. Lighting is not working (Objects are pitch black)
- **Symptom**: Model/mesh renders but appears solid black.
- **Fix**: You are likely using `MeshStandardMaterial` or `MeshPhysicalMaterial` which require lights to render. Make sure you added an `<ambientLight />` or `THREE.AmbientLight` to the scene. If using framework-free, check that the light coordinates target the object.

### 3. GLTF Models fail to load (CORS or Path Error)
- **Symptom**: `Failed to load resource: the server responded with a status of 404` or `CORS policy blocked access`.
- **Fix**: Store GLTF/GLB models inside the `public/` directory (e.g., `public/models/avatar.glb`). Address them using absolute paths relative to root: `/models/avatar.glb`, not local relative paths `./models/avatar.glb`.

---

## Verification

To verify that the 3D website renders and performs correctly:
1. Open Google Chrome Developer Tools.
2. Select the **Performance Monitor** tab (or search via Cmd/Ctrl + Shift + P -> "Show Performance Monitor").
3. Monitor the **CPU usage** and **FPS** (Target: stable 60 FPS).
4. Run a Lighthouse performance audit.
5. Resize the window and confirm that the canvas elements auto-resize and the camera aspect ratio maintains correct proportions without stretching the 3D meshes.
