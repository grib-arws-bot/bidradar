/**
 * BidRadar 로고 컴포넌트 — Target Lock
 *
 * 사용:
 *   <Logo />                       기본 (마크 + 워드마크, 라이트)
 *   <Logo variant="mark" />        마크만 (사이드바 축소, 파비콘 대체)
 *   <Logo tone="inverse" />        어두운 배경용
 *   <Logo tone="mono" />           단색 (인쇄·팩스·워터마크)
 *   <Logo size={30} showSub />     크기 지정 + "입찰 레이더" 병기
 *
 * 주의 — 마크는 24px 미만으로 쓰지 말 것. 그 아래는 favicon.svg(단순화 버전)를 쓴다.
 */
import { Box, Typography } from '@mui/material';

type Tone = 'light' | 'inverse' | 'mono';

interface LogoProps {
  variant?: 'full' | 'mark';
  tone?: Tone;
  size?: number;      // 마크 한 변 (px)
  showSub?: boolean;  // "입찰 레이더" 병기
}

const TONES: Record<Tone, { outer: string; inner: string; tick: string; blip: string; word: string; accent: string; sub: string }> = {
  light:   { outer: '#919EAB', inner: '#637381', tick: '#161C24', blip: '#DE5B21', word: '#161C24', accent: '#DE5B21', sub: '#919EAB' },
  inverse: { outer: '#454F5B', inner: '#919EAB', tick: '#E9E6E0', blip: '#FF9E6B', word: '#FFFFFF', accent: '#FF9E6B', sub: '#919EAB' },
  mono:    { outer: 'currentColor', inner: 'currentColor', tick: 'currentColor', blip: 'currentColor', word: 'currentColor', accent: 'currentColor', sub: 'currentColor' },
};

export function LogoMark({ tone = 'light', size = 40 }: { tone?: Tone; size?: number }) {
  const c = TONES[tone];
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" role="img" aria-label="BidRadar">
      <circle cx="24" cy="24" r="18" stroke={c.outer} strokeWidth="2.4" />
      <circle cx="24" cy="24" r="10.5" stroke={c.inner} strokeWidth="2.4" />
      <path d="M24 2v7M24 39v7M2 24h7M39 24h7" stroke={c.tick} strokeWidth="2.4" strokeLinecap="round" />
      <circle cx="31" cy="17" r="3.4" fill={c.blip} />
    </svg>
  );
}

export default function Logo({ variant = 'full', tone = 'light', size = 40, showSub = false }: LogoProps) {
  const c = TONES[tone];
  if (variant === 'mark') return <LogoMark tone={tone} size={size} />;

  return (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: `${Math.round(size * 0.3)}px` }}>
      <LogoMark tone={tone} size={size} />
      <Box>
        <Typography
          component="div"
          sx={{
            fontFamily: '"DM Sans","Noto Sans KR",sans-serif',
            fontWeight: 700,
            fontSize: `${Math.round(size * 0.65)}px`,
            letterSpacing: '-0.03em',
            lineHeight: 1,
          }}
        >
          <Box component="span" sx={{ color: c.word }}>Bid</Box>
          <Box component="span" sx={{ color: c.accent }}>Radar</Box>
        </Typography>
        {showSub && (
          <Typography
            component="div"
            sx={{
              fontSize: `${Math.round(size * 0.25)}px`,
              fontWeight: 700,
              letterSpacing: '0.16em',
              textTransform: 'uppercase',
              color: c.sub,
              mt: '4px',
              lineHeight: 1,
            }}
          >
            입찰 레이더
          </Typography>
        )}
      </Box>
    </Box>
  );
}
