import VisibilityIcon from "@mui/icons-material/VisibilityOutlined";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOffOutlined";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Box,
  Button,
  CircularProgress,
  Divider,
  IconButton,
  InputAdornment,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { checkIsDev, devAutologin, login } from "@/api/auth";

const schema = z.object({
  email: z.string().min(1, "이메일을 입력하세요"),
  password: z.string().min(1, "비밀번호를 입력하세요"),
});

type FormValues = z.infer<typeof schema>;

// 로컬 개발 전용 자동로그인(2026-09-01 요청) — is_dev일 때만 백엔드가 /auth/dev-autologin에
// 응답한다(그 외엔 404). 실패하면 조용히 일반 로그인 폼으로 넘어간다.
//
// 2026-09-03 — /api/health 조회가 retry:false라 컨테이너 재기동 직후처럼 한 번이라도
// 실패하면 isDev가 영영 undefined로 남아 자동로그인이 아예 시도조차 안 되는 채로 일반
// 폼만 보이는 문제가 있었다(사용자가 "자동로그인이 안 된다"고 보고한 원인으로 추정).
// retry를 2회로 늘리고, 자동 실행이 실패하거나 안 붙어도 눌러서 재시도할 수 있는 버튼을
// 폼에 항상 남겨둔다(isDev인 동안).
function useDevAutologin(onDone: () => void) {
  const [skipped, setSkipped] = useState(false);
  const { data: isDev } = useQuery({ queryKey: ["health-is-dev"], queryFn: checkIsDev, retry: 2, retryDelay: 500 });
  const mutation = useMutation({
    mutationFn: devAutologin,
    onSuccess: onDone,
    onError: () => setSkipped(true),
  });
  const { mutate } = mutation;

  useEffect(() => {
    if (isDev) mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDev]);

  return { isDev: isDev === true, active: isDev === true && !skipped, retry: () => mutate() };
}

export function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showPassword, setShowPassword] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors },
    setError,
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "report@grib.co.kr", password: "" },
  });

  const goToNotices = async () => {
    await queryClient.invalidateQueries({ queryKey: ["me"] });
    navigate("/notices", { replace: true });
  };

  const { isDev, active: autologinActive, retry: retryAutologin } = useDevAutologin(goToNotices);

  const mutation = useMutation({
    mutationFn: (values: FormValues) => login(values.email, values.password),
    onSuccess: goToNotices,
    onError: (error: unknown) => {
      const detail =
        (error as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
        "로그인에 실패했습니다.";
      setError("password", { message: detail });
    },
  });

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        bgcolor: "background.default",
      }}
    >
      <Paper elevation={3} sx={{ p: 5, width: 380 }}>
        <Stack spacing={0.5} sx={{ mb: 4 }}>
          <Typography variant="h2">BidRadar</Typography>
          <Typography variant="body2" color="text.secondary">
            사전규격 단계부터 보는 입찰 레이더
          </Typography>
        </Stack>
        {autologinActive ? (
          <Stack spacing={1.5} alignItems="center" sx={{ py: 3 }}>
            <CircularProgress size={28} />
            <Typography variant="body2" color="text.secondary">
              개발 환경 자동로그인 중...
            </Typography>
          </Stack>
        ) : (
          <Stack spacing={2}>
            {isDev && (
              <>
                <Button variant="outlined" size="large" onClick={retryAutologin} fullWidth>
                  개발 환경 자동 로그인
                </Button>
                <Divider>또는 직접 로그인</Divider>
              </>
            )}
            <Box component="form" onSubmit={handleSubmit((values) => mutation.mutate(values))}>
              <Stack spacing={2}>
                <TextField
                  label="이메일"
                  {...register("email")}
                  error={!!errors.email}
                  helperText={errors.email?.message}
                  fullWidth
                />
                <TextField
                  label="비밀번호"
                  type={showPassword ? "text" : "password"}
                  {...register("password")}
                  error={!!errors.password}
                  helperText={errors.password?.message}
                  fullWidth
                  slotProps={{
                    input: {
                      endAdornment: (
                        <InputAdornment position="end">
                          <IconButton
                            aria-label={showPassword ? "비밀번호 숨기기" : "비밀번호 보이기"}
                            onClick={() => setShowPassword((v) => !v)}
                            edge="end"
                            size="small"
                          >
                            {showPassword ? <VisibilityOffIcon fontSize="small" /> : <VisibilityIcon fontSize="small" />}
                          </IconButton>
                        </InputAdornment>
                      ),
                    },
                  }}
                />
                <Button type="submit" variant="contained" size="large" disabled={mutation.isPending} fullWidth>
                  로그인
                </Button>
              </Stack>
            </Box>
          </Stack>
        )}
      </Paper>
    </Box>
  );
}
