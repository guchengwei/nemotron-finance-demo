/** Deterministic SVG avatar generated from persona attributes. */

interface Props {
  name: string
  age: number
  sex: string
  size?: number
}

function hashStr(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) {
    h = (Math.imul(31, h) + s.charCodeAt(i)) | 0
  }
  return Math.abs(h)
}

const COLORS = [
  '#76B900', '#00A3E0', '#4ade80', '#60a5fa', '#a78bfa',
  '#f472b6', '#fb923c', '#34d399', '#38bdf8', '#818cf8',
]

export default function PersonaAvatar({ name, age, sex, size = 40 }: Props) {
  const h = hashStr(name + sex + age)
  const bgColor = COLORS[h % COLORS.length]
  const shape = h % 3  // 0=circle, 1=rounded square, 2=hexagon
  const initials = name.replace(/\s/g, '').slice(0, 2) || '?'

  const ageGroup = age < 30 ? 0 : age < 50 ? 1 : 2
  const opacity = 0.7 + ageGroup * 0.1

  return (
    <svg width={size} height={size} viewBox="0 0 40 40" style={{ flexShrink: 0 }}>
      {shape === 0 && (
        <circle cx="20" cy="20" r="18" fill={bgColor} opacity={opacity} />
      )}
      {shape === 1 && (
        <rect x="2" y="2" width="36" height="36" rx="8" fill={bgColor} opacity={opacity} />
      )}
      {shape === 2 && (
        <polygon
          points="20,2 37,11 37,29 20,38 3,29 3,11"
          fill={bgColor}
          opacity={opacity}
        />
      )}
      <text
        x="20"
        y="25"
        textAnchor="middle"
        fontSize="14"
        fontWeight="bold"
        fill="white"
        fontFamily="Noto Sans JP, sans-serif"
      >
        {initials}
      </text>
    </svg>
  )
}
