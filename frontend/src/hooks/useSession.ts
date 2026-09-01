import { useQuery } from "@tanstack/react-query";

import { fetchMe } from "@/api/auth";

export function useSession() {
  return useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
}
