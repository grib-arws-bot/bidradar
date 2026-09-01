import { zodResolver } from "@hookform/resolvers/zod";
import { Box, Button, Paper, Stack, TextField, Typography } from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { login } from "@/api/auth";

const schema = z.object({
  email: z.string().min(1, "이메일을 입력하세요"),
  password: z.string().min(1, "비밀번호를 입력하세요"),
});

type FormValues = z.infer<typeof schema>;

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

  const mutation = useMutation({
    mutationFn: (values: FormValues) => login(values.email, values.password),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      navigate("/notices", { replace: true });
    },
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
      <Paper elevation={0} sx={{ p: 5, width: 380, border: "1px dashed", borderColor: "grey.300" }}>
        <Stack spacing={0.5} sx={{ mb: 4 }}>
          <Typography variant="h2">BidRadar</Typography>
          <Typography variant="body2" color="text.secondary">
            사전규격 단계부터 보는 입찰 레이더
          </Typography>
        </Stack>
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
      </Paper>
    </Box>
  );
}
