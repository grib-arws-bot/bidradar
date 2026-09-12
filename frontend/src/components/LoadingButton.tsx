import { Button, type ButtonProps, CircularProgress, IconButton, type IconButtonProps } from "@mui/material";

// 시간이 걸리는 작업(AI 분석·리포트 생성·저장·발송 등) 버튼에서 "진행 중" 상태를 일관되게
// 보여주기 위한 공용 래퍼(2026-09-12 사용자 지시 — "시간이 걸리는 모든 작업에서 버튼에
// 진행중 움직이는 아이콘 형태를 보여줘"). @mui/lab의 LoadingButton을 새로 설치하는 대신
// 이미 쓰던 Button+CircularProgress 조합을 재사용 가능한 형태로 뺐다.
export function LoadingButton({
  loading,
  loadingText,
  startIcon,
  disabled,
  children,
  ...props
}: ButtonProps & { loading?: boolean; loadingText?: string }) {
  return (
    <Button
      {...props}
      disabled={disabled || loading}
      startIcon={loading ? <CircularProgress size={16} color="inherit" /> : startIcon}
    >
      {loading && loadingText ? loadingText : children}
    </Button>
  );
}

// 아이콘 하나만 있는 버튼(발송·삭제 등)용 — 진행 중엔 그 아이콘을 스피너로 바꾼다.
export function LoadingIconButton({
  loading,
  disabled,
  children,
  ...props
}: IconButtonProps & { loading?: boolean }) {
  return (
    <IconButton {...props} disabled={disabled || loading}>
      {loading ? <CircularProgress size={16} color="inherit" /> : children}
    </IconButton>
  );
}
