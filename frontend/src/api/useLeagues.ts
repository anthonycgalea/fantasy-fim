import { useQuery } from "@tanstack/react-query";
import { League } from "@/types/League";

export const useLeagues = () =>
  useQuery<League[]>({
    queryFn: () => fetch("/api/leagues").then((res) => res.json()),
    queryKey: ["leagues"],
  });
