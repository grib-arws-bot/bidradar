import { zodResolver } from "@hookform/resolvers/zod";
import { Box, Button, CircularProgress, Paper, Stack, TextField, Typography } from "@mui/material";
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
function useDevAutologin(onDone: () => void) {
  const [skipped, setSkipped] = useState(false);
  const { data: isDev } = useQuery({ queryKey: ["health-is-dev"], queryFn: checkIsDev, retry: false });
  const mutation = useMutation({
    mutationFn: devAutologin,
    onSuccess: onDone,
    onError: () => setSkipped(true),
  });
  const { mutate } = mutation;

  useEffect(() => {
    if (isDev) mutate();
    else if (isDev === false) setSkipped(true);
  }, [isDev, mutate]);

  return { active: isDev === true && !skipped };
}

export function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
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

  const { active: autologinActive } = useDevAutologin(goToNotices);

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
                type="password"
                {...register("password")}
                error={!!errors.password}
                helperText={errors.password?.message}
                fullWidth
              />
              <Button type="submit" variant="contained" size="large" disabled={mutation.isPending} fullWidth>
                로그인
              </Button>
            </Stack>
          </Box>
        )}
      </Paper>
    </Box>
  );
}
