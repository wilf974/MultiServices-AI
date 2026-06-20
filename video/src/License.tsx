import React from "react";
import {
  AbsoluteFill,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
  Easing,
} from "remotion";

export const LIC_FPS = 30;
export const LIC_DURATION = 1020; // 34s

const C = {
  bg: "#0a0e16",
  panel: "#111a2b",
  panelEdge: "#1e2c44",
  ink: "#e8eefb",
  muted: "#8a99b6",
  mint: "#3df5c4",
  blue: "#7aa2ff",
  warn: "#ff5d6c",
  gold: "#ffcf5c",
};
const MONO = "'SF Mono','DejaVu Sans Mono','Courier New',monospace";
const SANS = "'Segoe UI','Helvetica Neue',system-ui,sans-serif";

const useReveal = (delay: number, dur = 18) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame, [delay, delay + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  return { opacity: t, y: (1 - t) * 22 };
};

const Glow: React.FC = () => {
  const frame = useCurrentFrame();
  const drift = Math.sin(frame / 80) * 30;
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ background: C.bg }} />
      <div
        style={{
          position: "absolute",
          width: 1100,
          height: 1100,
          left: -200 + drift,
          top: -350,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(61,245,196,0.16), transparent 60%)",
          filter: "blur(20px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 1200,
          height: 1200,
          right: -300 - drift,
          bottom: -450,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(122,162,255,0.14), transparent 60%)",
          filter: "blur(20px)",
        }}
      />
      <AbsoluteFill
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px)",
          backgroundSize: "64px 64px",
          maskImage: "radial-gradient(circle at 50% 45%, black, transparent 80%)",
          WebkitMaskImage: "radial-gradient(circle at 50% 45%, black, transparent 80%)",
        }}
      />
      <AbsoluteFill style={{ boxShadow: "inset 0 0 320px rgba(0,0,0,0.75)" }} />
    </AbsoluteFill>
  );
};

// ---------- Scene 1 ----------
const Title: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 30 });
  const head = useReveal(30);
  const cap = useReveal(56);
  const fadeOut = interpolate(frame, [84, 100], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{ justifyContent: "center", alignItems: "center", textAlign: "center", opacity: fadeOut }}
    >
      <div
        style={{
          fontFamily: MONO,
          fontSize: 24,
          letterSpacing: 7,
          textTransform: "uppercase",
          color: C.mint,
          opacity: pop,
          transform: `translateY(${(1 - pop) * 14}px)`,
        }}
      >
        A true story — from its own memory
      </div>
      <div
        style={{
          fontFamily: SANS,
          fontWeight: 800,
          fontSize: 86,
          lineHeight: 1.08,
          marginTop: 24,
          maxWidth: 1400,
          color: C.ink,
          opacity: head.opacity,
          transform: `translateY(${head.y}px)`,
        }}
      >
        The memory remembers
        <br />
        <span style={{ color: C.mint }}>its own development.</span>
      </div>
      <div
        style={{
          fontFamily: MONO,
          fontSize: 26,
          marginTop: 30,
          color: C.muted,
          opacity: cap.opacity,
          transform: `translateY(${cap.y}px)`,
        }}
      >
        Every frame below is a real event from the journal.
      </div>
    </AbsoluteFill>
  );
};

// ---------- Scene 2: real journal rows ----------
const Strike: React.FC<{ delay: number; children: React.ReactNode }> = ({ delay, children }) => {
  const frame = useCurrentFrame();
  const w = interpolate(frame, [delay, delay + 16], [0, 100], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <span style={{ position: "relative", color: C.muted }}>
      {children}
      <span
        style={{
          position: "absolute",
          left: 0,
          top: "52%",
          height: 3,
          width: `${w}%`,
          background: C.warn,
          boxShadow: `0 0 10px ${C.warn}`,
        }}
      />
    </span>
  );
};

const Row: React.FC<{
  delay: number;
  tag: string;
  meta: string;
  tagColor: string;
  text: React.ReactNode;
  note?: React.ReactNode;
  strikeDelay?: number;
}> = ({ delay, tag, meta, tagColor, text, note }) => {
  const r = useReveal(delay);
  return (
    <div style={{ opacity: r.opacity, transform: `translateY(${r.y}px)` }}>
      <div
        style={{
          background: C.panel,
          border: `1px solid ${C.panelEdge}`,
          borderLeft: `4px solid ${tagColor}`,
          borderRadius: 14,
          padding: "22px 30px",
          width: 1180,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <div
            style={{
              fontFamily: MONO,
              fontSize: 20,
              letterSpacing: 3,
              color: tagColor,
              textTransform: "uppercase",
            }}
          >
            {tag}
          </div>
          <div style={{ fontFamily: MONO, fontSize: 18, color: C.muted }}>{meta}</div>
        </div>
        <div style={{ fontFamily: SANS, fontSize: 40, fontWeight: 700, color: C.ink, marginTop: 10 }}>
          {text}
        </div>
        {note ? <div style={{ marginTop: 12 }}>{note}</div> : null}
      </div>
    </div>
  );
};

const Timeline: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useReveal(4);
  const fadeOut = interpolate(frame, [335, 360], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", opacity: fadeOut }}>
      <div
        style={{
          fontFamily: SANS,
          fontSize: 34,
          color: C.ink,
          marginBottom: 40,
          opacity: head.opacity,
          transform: `translateY(${head.y}px)`,
        }}
      >
        Choosing a license — captured as it happened.{" "}
        <span style={{ fontFamily: MONO, fontSize: 24, color: C.muted }}>session: licence</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
        <Row
          delay={36}
          tag="Decision"
          meta="user:local · Jun 19, 20:14"
          tagColor={C.gold}
          text="License: MIT — the simple, permissive default."
        />
        <Row
          delay={120}
          tag="Correction"
          meta="project:local · Jun 19, 20:34"
          tagColor={C.warn}
          text={
            <span>
              Actually not <Strike delay={180}>MIT</Strike> →{" "}
              <span style={{ color: C.mint }}>Apache-2.0</span>.
            </span>
          }
          note={
            <div>
              <div style={{ fontFamily: SANS, fontSize: 26, color: C.ink }}>
                …for the explicit patent grant on an original concept.
              </div>
              <div
                style={{
                  fontFamily: MONO,
                  fontSize: 20,
                  color: C.warn,
                  marginTop: 10,
                }}
              >
                supersedes the MIT decision — C3: closed, never deleted
              </div>
            </div>
          }
        />
      </div>
    </AbsoluteFill>
  );
};

// ---------- Scene 3: what the memory does ----------
const ToolPanel: React.FC<{
  delay: number;
  call: string;
  width: number;
  children: React.ReactNode;
}> = ({ delay, call, width, children }) => {
  const r = useReveal(delay);
  return (
    <div
      style={{
        width,
        background: "#0c1424",
        border: `1px solid ${C.panelEdge}`,
        borderRadius: 16,
        padding: 30,
        opacity: r.opacity,
        transform: `translateY(${r.y}px)`,
        boxShadow: "0 0 50px rgba(0,0,0,0.4)",
      }}
    >
      <div style={{ fontFamily: MONO, fontSize: 24, color: C.blue, marginBottom: 20 }}>
        <span style={{ color: C.muted }}>$</span> {call}
      </div>
      {children}
    </div>
  );
};

const Line: React.FC<{ delay: number; children: React.ReactNode }> = ({ delay, children }) => {
  const r = useReveal(delay);
  return (
    <div
      style={{
        opacity: r.opacity,
        transform: `translateX(${r.y}px)`,
        marginTop: 10,
        fontFamily: MONO,
        fontSize: 27,
      }}
    >
      {children}
    </div>
  );
};

const Memory: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useReveal(4);
  const foot = useReveal(250);
  const fadeOut = interpolate(frame, [355, 380], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", opacity: fadeOut }}>
      <div
        style={{
          fontFamily: SANS,
          fontSize: 36,
          fontWeight: 700,
          color: C.ink,
          marginBottom: 40,
          opacity: head.opacity,
          transform: `translateY(${head.y}px)`,
        }}
      >
        30 days later — what the memory does with it.
      </div>
      <div style={{ display: "flex", gap: 36, alignItems: "flex-start" }}>
        <ToolPanel delay={30} call='recall("license")' width={560}>
          <Line delay={60}>
            <span style={{ color: C.mint }}>Apache-2.0</span>{" "}
            <span style={{ color: C.muted }}>· current truth ✓</span>
          </Line>
          <Line delay={95}>
            <span style={{ color: C.muted, textDecoration: "line-through" }}>MIT</span>{" "}
            <span
              style={{
                color: C.warn,
                border: `1px solid ${C.warn}`,
                borderRadius: 8,
                padding: "2px 9px",
                fontSize: 19,
              }}
            >
              STALE · C3
            </span>
          </Line>
        </ToolPanel>

        <ToolPanel delay={130} call="lessons()" width={620}>
          <Line delay={160}>
            <span style={{ color: C.gold }}>MIT</span>{" "}
            <span style={{ color: C.muted }}>→</span>{" "}
            <span style={{ color: C.mint }}>Apache-2.0</span>
          </Line>
          <Line delay={195}>
            <span style={{ color: C.muted }}>why:</span> explicit patent grant
          </Line>
          <Line delay={222}>
            <span style={{ color: C.muted }}>still_standing:</span>{" "}
            <span style={{ color: C.mint }}>Apache-2.0</span>
          </Line>
        </ToolPanel>
      </div>
      <div
        style={{
          fontFamily: SANS,
          fontSize: 30,
          color: C.ink,
          marginTop: 46,
          maxWidth: 1180,
          textAlign: "center",
          opacity: foot.opacity,
          transform: `translateY(${foot.y}px)`,
        }}
      >
        The MIT decision was never deleted — only{" "}
        <span style={{ color: C.mint }}>closed</span>. The memory still explains{" "}
        <span style={{ color: C.mint }}>why</span> the truth changed.
      </div>
    </AbsoluteFill>
  );
};

// ---------- Scene 4 ----------
const Closing: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 34 });
  const sub = useReveal(30);
  const url = useReveal(54);
  const chips = useReveal(74);
  const fadeIn = interpolate(frame, [0, 16], [0, 1], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill
      style={{ justifyContent: "center", alignItems: "center", textAlign: "center", opacity: fadeIn }}
    >
      <div
        style={{
          fontFamily: SANS,
          fontSize: 58,
          fontWeight: 800,
          lineHeight: 1.16,
          maxWidth: 1350,
          color: C.ink,
          transform: `scale(${0.94 + pop * 0.06})`,
        }}
      >
        The project uses its own memory
        <br />
        to remember <span style={{ color: C.mint }}>its own evolution.</span>
      </div>
      <div
        style={{
          fontFamily: MONO,
          fontSize: 26,
          color: C.muted,
          marginTop: 28,
          opacity: sub.opacity,
          transform: `translateY(${sub.y}px)`,
        }}
      >
        Knowledge that explains why a truth changed.
      </div>
      <div
        style={{
          fontFamily: MONO,
          fontSize: 32,
          color: C.blue,
          marginTop: 36,
          opacity: url.opacity,
          transform: `translateY(${url.y}px)`,
        }}
      >
        github.com/wilf974/MultiServices-AI
      </div>
      <div
        style={{
          fontFamily: MONO,
          fontSize: 23,
          color: C.muted,
          marginTop: 24,
          letterSpacing: 2,
          opacity: chips.opacity,
          transform: `translateY(${chips.y}px)`,
        }}
      >
        Apache-2.0 &nbsp;·&nbsp; 100% local &nbsp;·&nbsp; MCP-native &nbsp;·&nbsp; bi-temporal
      </div>
    </AbsoluteFill>
  );
};

export const License: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Glow />
      <Sequence durationInFrames={100}>
        <Title />
      </Sequence>
      <Sequence from={100} durationInFrames={360}>
        <Timeline />
      </Sequence>
      <Sequence from={460} durationInFrames={380}>
        <Memory />
      </Sequence>
      <Sequence from={840} durationInFrames={180}>
        <Closing />
      </Sequence>
    </AbsoluteFill>
  );
};
