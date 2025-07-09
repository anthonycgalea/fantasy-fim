import { useQuery } from "@tanstack/react-query";
import { WeekStatus } from "../types/WeekStatus";

export const useCurrentWeek = () =>
  useQuery<WeekStatus>({
    queryFn: () => fetch('/api/currentWeek').then((res) => res.json()),
    queryKey: ['currentWeek'],
  });
