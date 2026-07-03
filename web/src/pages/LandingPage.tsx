import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useRef, useState, useEffect } from "react";
import { Link } from "react-router-dom";
import * as THREE from "three";
import { 
  ArrowRight, 
  Database, 
  Zap, 
  Github, 
  ExternalLink,
  MessageSquare,
  RefreshCw,
  Eye,
  TerminalSquare
} from "lucide-react";

// ── 3D CAMERA RIG (INERTIA + MOUSE FOCUS + PARALLAX SCROLL) ──
function CameraRig({ scrollOffset }: { scrollOffset: number }) {
  const { camera } = useThree();
  
  useFrame((state) => {
    // 1. Mouse coordinates mapped to minor tilting
    const targetX = state.pointer.x * 1.5;
    const targetY = state.pointer.y * 1.0;
    
    // 2. Scroll offset mapped to depth (zoom in as you scroll) and vertical pan
    const targetZ = 4.8 - scrollOffset * 2.5;
    const targetPanY = -scrollOffset * 3.0;

    // 3. Smooth interpolation (lerp) for inertia feel
    camera.position.x = THREE.MathUtils.lerp(camera.position.x, targetX, 0.05);
    camera.position.y = THREE.MathUtils.lerp(camera.position.y, targetPanY + targetY, 0.05);
    camera.position.z = THREE.MathUtils.lerp(camera.position.z, targetZ, 0.05);
    
    // Look slightly ahead of camera path
    camera.lookAt(0, targetPanY, 0);
  });
  
  return null;
}

// ── 3D CYBERNETIC MESH (YUTA ABE STYLE GEOMETRIC REFRACTION CORE) ──
function RefractionCore({ scrollOffset }: { scrollOffset: number }) {
  const groupRef = useRef<THREE.Group>(null);
  const ring1Ref = useRef<THREE.Mesh>(null);
  const ring2Ref = useRef<THREE.Mesh>(null);
  const innerRef = useRef<THREE.Mesh>(null);
  
  useFrame((state) => {
    const elapsed = state.clock.getElapsedTime();
    
    if (groupRef.current) {
      // Rotation affected by time and scroll speed
      groupRef.current.rotation.y = elapsed * 0.15 + scrollOffset * Math.PI;
      groupRef.current.rotation.x = Math.sin(elapsed * 0.1) * 0.2;
    }
    
    if (ring1Ref.current) {
      ring1Ref.current.rotation.x = elapsed * 0.5;
      ring1Ref.current.rotation.y = elapsed * 0.3;
    }
    
    if (ring2Ref.current) {
      ring2Ref.current.rotation.y = -elapsed * 0.4;
      ring2Ref.current.rotation.z = elapsed * 0.6;
    }

    if (innerRef.current) {
      // Pulsing scale based on sine wave
      const scale = 1.0 + Math.sin(elapsed * 3) * 0.08;
      innerRef.current.scale.set(scale, scale, scale);
    }
  });

  return (
    <group ref={groupRef}>
      {/* Central Glassmorphic Node */}
      <mesh ref={innerRef}>
        <octahedronGeometry args={[0.7, 0]} />
        <meshPhysicalMaterial
          color="#FF007F"
          roughness={0.1}
          metalness={0.1}
          transmission={0.8}
          thickness={1.5}
          emissive="#FF007F"
          emissiveIntensity={1.0}
          clearcoat={1.0}
        />
      </mesh>

      {/* Gyroscopic Tech Ring 1 (Cyan Neon) */}
      <mesh ref={ring1Ref}>
        <torusGeometry args={[1.3, 0.05, 8, 64]} />
        <meshStandardMaterial
          color="#00F0FF"
          emissive="#00F0FF"
          emissiveIntensity={2.5}
          wireframe
        />
      </mesh>

      {/* Gyroscopic Tech Ring 2 (Purple Neon) */}
      <mesh ref={ring2Ref}>
        <torusGeometry args={[1.6, 0.03, 6, 48]} />
        <meshStandardMaterial
          color="#BF5FFF"
          emissive="#BF5FFF"
          emissiveIntensity={2.0}
          wireframe
        />
      </mesh>

      {/* Outer Floating Vertices Grid */}
      <mesh>
        <dodecahedronGeometry args={[2.0, 1]} />
        <meshBasicMaterial
          color="#ffffff"
          wireframe
          transparent
          opacity={0.08}
        />
      </mesh>
    </group>
  );
}

// ── 3D PARTICLES FIELD (ORBITING STAR DUST) ──
function ParticleOrbit({ count = 300 }) {
  const pointsRef = useRef<THREE.Points>(null);
  
  const positions = Array.from({ length: count * 3 }, () => (Math.random() - 0.5) * 10);
  
  useFrame((state) => {
    if (pointsRef.current) {
      pointsRef.current.rotation.y = state.clock.getElapsedTime() * 0.02;
    }
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[new Float32Array(positions), 3]}
        />
      </bufferGeometry>
      <pointsMaterial
        size={0.035}
        color="#00F0FF"
        sizeAttenuation
        transparent
        opacity={0.4}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

export default function LandingPage() {
  const [scrollOffset, setScrollOffset] = useState(0);

  useEffect(() => {
    const handleScroll = () => {
      const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
      if (maxScroll <= 0) return;
      const offset = window.scrollY / maxScroll;
      setScrollOffset(offset);
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <div className="relative min-h-screen w-full bg-[#030307] text-[#e6edf3] overflow-x-hidden font-sans selection:bg-[#BF5FFF]/30">
      
      {/* ── Fixed Tech HUD telemetry reads (yutaabe.com style) ── */}
      <div className="fixed top-8 left-8 z-50 pointer-events-none hidden lg:block font-mono text-[9px] text-[#00F0FF]/40 tracking-widest space-y-1">
        <div>SYS_STATUS: ACTIVE</div>
        <div>NEXUS_DAEMON: ONLINE // {Math.round(scrollOffset * 100)}% DEPTH</div>
        <div>CRAWLER_COUNT: 11</div>
      </div>
      <div className="fixed top-8 right-8 z-50 pointer-events-none hidden lg:block font-mono text-[9px] text-[#BF5FFF]/40 tracking-widest text-right space-y-1">
        <div>CREATOR: CHARAN VANKUDOTH</div>
        <div>ALEX_BUILD_ID: SSS_SHADOW_MONARCH</div>
        <div>STABLE_STABILIZERS: STABLE</div>
      </div>

      {/* ── 3D Interactive Canvas (Sticky behind content) ── */}
      <div className="fixed inset-0 w-full h-full pointer-events-none z-0">
        <Canvas camera={{ position: [0, 0, 4.8], fov: 55 }}>
          <ambientLight intensity={0.2} />
          <directionalLight position={[5, 10, 5]} intensity={1.5} color="#BF5FFF" />
          <directionalLight position={[-5, -10, -5]} intensity={1.0} color="#00F0FF" />
          <pointLight position={[0, 0, 0]} intensity={2.0} color="#FF007F" />
          <RefractionCore scrollOffset={scrollOffset} />
          <ParticleOrbit count={350} />
          <CameraRig scrollOffset={scrollOffset} />
        </Canvas>
      </div>

      {/* ── Ambient Background Shadows & Radial Gradients ── */}
      <div className="fixed inset-0 pointer-events-none z-0 bg-[radial-gradient(circle_at_center,transparent_40%,#030307_95%)]" />

      {/* ── PAGE CONTENT WRAPPER (Scrollable) ── */}
      <div className="relative z-10 mx-auto max-w-7xl px-6 lg:px-8">
        
        {/* ── NAVIGATION HEADER ── */}
        <header className="flex justify-between items-center py-8 border-b border-white/[0.03]">
          <div className="flex items-center gap-3">
            <span className="text-[#00F0FF] font-bold text-xl tracking-[0.3em] uppercase select-none drop-shadow-[0_0_10px_rgba(0,240,255,0.4)]">
              ALEX AGENT
            </span>
          </div>
          <div className="flex items-center gap-6">
            <a 
              href="https://github.com/charan vankudoth/alex-agent" 
              target="_blank" 
              rel="noopener noreferrer"
              className="text-white/65 hover:text-white transition-colors duration-300"
            >
              <Github className="size-5" />
            </a>
            <Link 
              to="/sessions"
              className="px-6 py-2.5 text-xs font-bold tracking-[0.2em] uppercase bg-transparent border border-[#00F0FF]/50 text-[#00F0FF] hover:bg-[#00F0FF] hover:text-black rounded-sm shadow-[inset_0_0_10px_rgba(0,240,255,0.1),0_0_15px_rgba(0,240,255,0.2)] transition-all duration-300"
            >
              ENTER DASHBOARD
            </Link>
          </div>
        </header>

        {/* ── HERO SECTION ── */}
        <section className="min-h-[90vh] flex flex-col justify-center items-center text-center max-w-4xl mx-auto pt-12">
          {/* Pulsing Core Status Indicator */}
          <div className="inline-flex items-center gap-3 px-4 py-1.5 text-[10px] font-bold uppercase tracking-[0.2em] bg-black/60 border border-white/10 text-white rounded-full mb-10 shadow-[inset_0_0_8px_rgba(255,255,255,0.05)]">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#00F0FF] opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-[#00F0FF]"></span>
            </span>
            SYSTEM REVOLUTION ENGINE ACTIVATED
          </div>

          <h1 className="text-5xl sm:text-8xl font-black tracking-tight leading-[0.9] select-none text-white uppercase">
            THE AUTONOMOUS
            <span className="block mt-4 bg-gradient-to-r from-[#00F0FF] via-[#BF5FFF] to-[#FF007F] bg-clip-text text-transparent filter drop-shadow-[0_0_30px_rgba(0,240,255,0.35)] font-extrabold">
              EVOLUTION ENGINE
            </span>
          </h1>

          <p className="mt-10 text-base sm:text-lg text-white/60 font-light tracking-wide leading-relaxed max-w-2xl">
            A state-of-the-art AI agent that doesn't just code — **it self-merges and improves itself**. Driven by Project Nexus, it scans local directories and online registries, isolated-sandboxes code inputs, security-audits syntax, and upgrades its own codebase on the fly.
          </p>

          <div className="flex flex-wrap gap-5 justify-center mt-12">
            <Link
              to="/sessions"
              className="inline-flex items-center gap-3 px-8 py-4 text-xs font-bold uppercase tracking-[0.2em] bg-[#BF5FFF] text-white hover:bg-[#a549e5] rounded-sm shadow-[0_0_25px_rgba(191,95,255,0.4)] transition-all duration-300"
            >
              LAUNCH CONSOLE
              <ArrowRight className="size-4" />
            </Link>
            <a
              href="https://alex-agent.charan vankudoth.com/docs/"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-3 px-8 py-4 text-xs font-bold uppercase tracking-[0.2em] bg-transparent border border-white/10 hover:border-white/30 text-white rounded-sm transition-all duration-300"
            >
              EXPLORE CODEBASE
              <ExternalLink className="size-4" />
            </a>
          </div>
        </section>

        {/* ── CREATOR PROFILE HYPER-PANEL ── */}
        <section className="mt-16 py-20 border-t border-b border-white/[0.03] backdrop-blur-sm bg-black/20 rounded-3xl">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
            
            {/* Left Column: Glassmorphic Floating Creator Card */}
            <div className="lg:col-span-5 relative flex justify-center items-center">
              <div className="absolute w-[300px] h-[300px] bg-[#00F0FF]/10 rounded-full blur-[100px] pointer-events-none" />
              <div className="relative group overflow-hidden rounded-2xl border border-white/10 bg-[#07070f]/80 p-4 transform hover:scale-[1.03] transition-all duration-500 shadow-[0_0_50px_rgba(0,0,0,0.8)]">
                <img 
                  src="/creator.png" 
                  alt="Vankudoth Charan" 
                  className="rounded-xl max-h-[380px] w-auto object-cover filter drop-shadow-[0_0_20px_rgba(0,240,255,0.25)] group-hover:scale-[1.01] transition-transform duration-500"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-80" />
                <div className="absolute bottom-6 left-6 right-6 p-4 rounded-xl backdrop-blur-md bg-black/60 border border-white/10 text-center space-y-1">
                  <div className="text-[10px] font-bold uppercase tracking-[0.25em] text-[#00F0FF]">
                    LEAD ARCHITECT
                  </div>
                  <div className="text-xs text-white/50 font-mono tracking-wider">
                    CREATOR: VANKUDOTH CHARAN
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column: Platform Capabilities */}
            <div className="lg:col-span-7 space-y-8">
              <div className="space-y-3">
                <span className="text-[10px] font-bold uppercase tracking-[0.3em] text-[#BF5FFF]">
                  CORE REVOLUTION
                </span>
                <h2 className="text-4xl sm:text-5xl font-black tracking-tight text-white uppercase leading-none">
                  VANKUDOTH CHARAN // <br />
                  CREATOR OF MYTHOS-5
                </h2>
              </div>
              
              <p className="text-white/60 leading-relaxed font-light text-base sm:text-lg">
                Alex Agent is designed under the vision of Vankudoth Charan, the creator of the Mythos-5 experimental architecture series. Emphasizing extreme speed, automated validation, and deep file workspace manipulation, this system represents a significant milestone in agentic code generation.
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <div className="flex gap-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm bg-[#00F0FF]/15 border border-[#00F0FF]/30 text-[#00F0FF]">
                    <Database className="size-5" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold uppercase tracking-wider mb-1">AST Security Audit</h4>
                    <p className="text-xs text-white/50 font-light leading-relaxed">
                      Automatically scans all incoming code structures to identify and block malicious code injections before staging.
                    </p>
                  </div>
                </div>

                <div className="flex gap-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm bg-[#BF5FFF]/15 border border-[#BF5FFF]/30 text-[#BF5FFF]">
                    <Zap className="size-5" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold uppercase tracking-wider mb-1">Sandbox Validation</h4>
                    <p className="text-xs text-white/50 font-light leading-relaxed">
                      Imports code inside transient, isolated sub-environments to test functionality and verify library compatibility.
                    </p>
                  </div>
                </div>

                <div className="flex gap-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm bg-[#FF007F]/15 border border-[#FF007F]/30 text-[#FF007F]">
                    <RefreshCw className="size-5" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold uppercase tracking-wider mb-1">Atomic Rollbacks</h4>
                    <p className="text-xs text-white/50 font-light leading-relaxed">
                      Creates instant backups and stores rollback keys in an immutable changelog, safeguarding workspace integrity.
                    </p>
                  </div>
                </div>

                <div className="flex gap-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm bg-[#00F0FF]/15 border border-[#00F0FF]/30 text-[#00F0FF]">
                    <Eye className="size-5" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold uppercase tracking-wider mb-1">Offline Local Ingestion</h4>
                    <p className="text-xs text-white/50 font-light leading-relaxed">
                      Drop skills/tools at `%LOCALAPPDATA%\alex\nexus\incoming\` to train the agent offline without any internet connection.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── CORE CAPABILITIES GRID (Chats, Apps, MCPs, Skills, Customizations, Desktop App Teaser) ── */}
        <section className="mt-32 space-y-16">
          <div className="text-center space-y-3">
            <span className="text-[10px] font-bold uppercase tracking-[0.3em] text-[#00F0FF]">
              SYSTEM ENGINE CAPABILITIES
            </span>
            <h2 className="text-4xl sm:text-6xl font-black uppercase tracking-tight text-white leading-none">
              ALL-IN-ONE AGENT WORKSPACE
            </h2>
            <p className="text-white/50 max-w-2xl mx-auto font-light text-sm sm:text-base">
              Alex Agent acts as a central workspace for advanced development, equipped with tools, skills, and model integrations.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            
            {/* Feature 1: ChatGPT-Style Chat */}
            <div className="border border-white/5 bg-black/40 p-8 rounded-2xl backdrop-blur-md hover:border-[#00F0FF]/30 transition-all duration-300 group space-y-4">
              <div className="size-10 rounded-sm bg-[#00F0FF]/10 border border-[#00F0FF]/30 flex items-center justify-center text-[#00F0FF]">
                <MessageSquare className="size-5" />
              </div>
              <h3 className="text-lg font-bold uppercase tracking-wider text-white">ChatGPT-Style Chat</h3>
              <p className="text-xs text-white/50 leading-relaxed font-light">
                An interactive chat workspace designed for natural language instructions. Seamlessly handles streaming, agent reasoning steps, and prompts. Connects automatically or runs in simulated Demo Mode.
              </p>
            </div>

            {/* Feature 2: Website & App Creation */}
            <div className="border border-white/5 bg-black/40 p-8 rounded-2xl backdrop-blur-md hover:border-[#BF5FFF]/30 transition-all duration-300 group space-y-4">
              <div className="size-10 rounded-sm bg-[#BF5FFF]/10 border border-[#BF5FFF]/30 flex items-center justify-center text-[#BF5FFF]">
                <svg className="size-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 00-2 2z" />
                </svg>
              </div>
              <h3 className="text-lg font-bold uppercase tracking-wider text-white">App & Website Creation</h3>
              <p className="text-xs text-white/50 leading-relaxed font-light">
                Generates responsive static websites and fullstack applications with one click. Spawns template runtimes, structures code blocks, installs dependencies, and runs live local preview servers.
              </p>
            </div>

            {/* Feature 3: Model Context Protocol (MCP) */}
            <div className="border border-white/5 bg-black/40 p-8 rounded-2xl backdrop-blur-md hover:border-[#FF007F]/30 transition-all duration-300 group space-y-4">
              <div className="size-10 rounded-sm bg-[#FF007F]/10 border border-[#FF007F]/30 flex items-center justify-center text-[#FF007F]">
                <Database className="size-5" />
              </div>
              <h3 className="text-lg font-bold uppercase tracking-wider text-white">MCP Integrations</h3>
              <p className="text-xs text-white/50 leading-relaxed font-light">
                Integrate custom Model Context Protocol servers (like StitchMCP, SQLite, and Git tools) directly. Streamline file reads, structural queries, databases, and secure third-party credentials.
              </p>
            </div>

            {/* Feature 4: Custom Skills & Rules */}
            <div className="border border-white/5 bg-black/40 p-8 rounded-2xl backdrop-blur-md hover:border-[#FF007F]/30 transition-all duration-300 group space-y-4">
              <div className="size-10 rounded-sm bg-[#FF007F]/10 border border-[#FF007F]/30 flex items-center justify-center text-[#FF007F]">
                <svg className="size-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                </svg>
              </div>
              <h3 className="text-lg font-bold uppercase tracking-wider text-white">Customization Engine</h3>
              <p className="text-xs text-white/50 leading-relaxed font-light">
                Inject custom instructions, style guides, and rulesets using `AGENTS.md` and standard Markdown files. Define custom coding behaviors and keep your agent tailored to your workflow.
              </p>
            </div>

            {/* Feature 5: Advanced Coding Personas */}
            <div className="border border-white/5 bg-black/40 p-8 rounded-2xl backdrop-blur-md hover:border-[#00F0FF]/30 transition-all duration-300 group space-y-4">
              <div className="size-10 rounded-sm bg-[#00F0FF]/10 border border-[#00F0FF]/30 flex items-center justify-center text-[#00F0FF]">
                <TerminalSquare className="size-5" />
              </div>
              <h3 className="text-lg font-bold uppercase tracking-wider text-white">Advanced Agent Runtimes</h3>
              <p className="text-xs text-white/50 leading-relaxed font-light">
                Orchestrates multi-agent coordinate graphs including Project Planner, Code Architect, DevOps, QA, and closed-loop Debugger personas, executing complex tasks with automated verification.
              </p>
            </div>

            {/* Feature 6: Desktop App Roadmap */}
            <div className="border border-[#BF5FFF]/20 bg-gradient-to-br from-[#BF5FFF]/5 to-transparent p-8 rounded-2xl backdrop-blur-md hover:border-[#BF5FFF]/50 transition-all duration-300 group space-y-4 relative overflow-hidden">
              <div className="absolute top-2 right-2 px-2 py-0.5 text-[8px] font-mono tracking-widest text-[#BF5FFF] border border-[#BF5FFF]/30 bg-[#BF5FFF]/10 uppercase rounded">
                Roadmap
              </div>
              <div className="size-10 rounded-sm bg-[#BF5FFF]/10 border border-[#BF5FFF]/30 flex items-center justify-center text-[#BF5FFF]">
                <svg className="size-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                </svg>
              </div>
              <h3 className="text-lg font-bold uppercase tracking-wider text-white">Native Desktop App</h3>
              <p className="text-xs text-white/50 leading-relaxed font-light">
                A native Tauri desktop application is planned to launch later! Features deep operating system terminal binds, local file listeners, automated sandboxes, and secure credential managers.
              </p>
            </div>

          </div>
        </section>

        {/* ── SAAS METRICS AND SPEED ── */}
        <section className="mt-32 space-y-16">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
            <div className="space-y-6">
              <span className="text-[10px] font-bold uppercase tracking-[0.3em] text-[#00F0FF]">
                PLATFORM CHASSIS
              </span>
              <h2 className="text-3xl sm:text-5xl font-black uppercase tracking-tight leading-none">
                BUILT FOR MASSIVE SPEED.
              </h2>
              <p className="text-white/60 font-light leading-relaxed">
                We've tuned the agent configuration to achieve peak performance. The entire codebase compiles asynchronously in memory, featuring instant hot-reloading.
              </p>
              <div className="grid grid-cols-3 gap-6 pt-4 text-center sm:text-left">
                <div>
                  <div className="text-3xl font-black text-[#00F0FF]">~400ms</div>
                  <div className="text-[9px] uppercase tracking-wider text-white/40 mt-1">Startup Delay</div>
                </div>
                <div>
                  <div className="text-3xl font-black text-[#BF5FFF]">20+</div>
                  <div className="text-[9px] uppercase tracking-wider text-white/40 mt-1">Platforms</div>
                </div>
                <div>
                  <div className="text-3xl font-black text-[#FF007F]">6</div>
                  <div className="text-[9px] uppercase tracking-wider text-white/40 mt-1">Backends</div>
                </div>
              </div>
            </div>

            {/* Premium 3D Tech HUD features block */}
            <div className="border border-white/5 rounded-2xl bg-black/40 p-8 backdrop-blur-md space-y-6 relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-[#00F0FF]/5 rounded-bl-full filter blur-xl" />
              <div className="flex items-center gap-3 pb-4 border-b border-white/5">
                <TerminalSquare className="size-5 text-[#00F0FF]" />
                <span className="text-xs font-bold uppercase tracking-wider">TUI Gateway Console</span>
              </div>
              <div className="space-y-4 font-mono text-xs text-white/60">
                <div className="flex justify-between">
                  <span className="text-white/40">ENGINE_MODE:</span>
                  <span className="text-[#00F0FF]">FULL_AUTO</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-white/40">AST_SECURITY:</span>
                  <span className="text-green-400">SECURE // ENFORCED</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-white/40">MEMORY_INDEX:</span>
                  <span className="text-[#BF5FFF]">FTS5_ACTIVE</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-white/40">DAYTONA_RUNTIMES:</span>
                  <span className="text-[#FF007F]">PROVISIONED</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── THE ARCHITECT PANEL ── */}
        <section className="mt-32 border border-white/5 rounded-2xl bg-gradient-to-b from-white/[0.01] to-transparent p-8 sm:p-16 text-center max-w-4xl mx-auto space-y-8 relative overflow-hidden">
          <div className="absolute -top-24 left-1/2 -translate-x-1/2 w-80 h-80 bg-[#FF007F]/10 rounded-full blur-[90px] pointer-events-none" />
          
          <span className="text-[10px] font-bold uppercase tracking-[0.3em] text-[#FF007F]">
            ORIGIN // AUTHOR
          </span>
          
          <h2 className="text-4xl sm:text-6xl font-black uppercase tracking-tight text-white">
            Charan Vankudoth
          </h2>
          
          <p className="text-white/65 font-light leading-relaxed max-w-xl mx-auto text-sm sm:text-base">
            Alex Agent is the official self-evolving coder model designed by **Charan Vankudoth**—the lab behind next-generation AI pipelines. Combining dynamic code generation, AST-level safety visitors, and multi-protocol gateways, this agent is constructed to learn continuously from the global developer ecosystem.
          </p>

          <div className="flex gap-4 justify-center flex-wrap pt-4">
            <a 
              href="https://github.com/anxcrn" 
              target="_blank" 
              rel="noopener noreferrer"
              className="inline-flex items-center gap-3 px-6 py-3.5 text-xs font-bold uppercase tracking-wider bg-white/5 border border-white/10 hover:bg-white/10 rounded-sm transition-all"
            >
              Developer Profile
              <ExternalLink className="size-4" />
            </a>
            <a 
              href="https://discord.gg/charan vankudoth" 
              target="_blank" 
              rel="noopener noreferrer"
              className="inline-flex items-center gap-3 px-6 py-3.5 text-xs font-bold uppercase tracking-wider bg-[#5865F2]/10 border border-[#5865F2]/30 hover:bg-[#5865F2]/30 rounded-sm text-[#8EA8FF] transition-all"
            >
              Join developer community
              <MessageSquare className="size-4" />
            </a>
          </div>
        </section>

        {/* ── FOOTER ── */}
        <footer className="mt-40 py-12 border-t border-white/[0.03] flex flex-col sm:flex-row justify-between items-center gap-4 text-[10px] tracking-wider uppercase text-white/30 font-mono">
          <div>
            Created by <a href="https://charan vankudoth.com" className="hover:text-white transition-colors">charan vankudoth</a>. Licensed under MIT.
          </div>
          <div className="flex gap-8">
            <a href="https://github.com/charan vankudoth/alex-agent" className="hover:text-white transition-colors">GitHub</a>
            <Link to="/docs" className="hover:text-white transition-colors">Docs</Link>
            <Link to="/sessions" className="hover:text-white transition-colors">Dashboard</Link>
          </div>
        </footer>

      </div>
    </div>
  );
}
