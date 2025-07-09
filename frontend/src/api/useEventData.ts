import { useQuery } from "@tanstack/react-query";
import { EventData } from "@/types/EventData";

export const useEventData = () =>
  useQuery<EventData[]>({
    queryFn: () => fetch("/api/eventData").then((res) => res.json()),
    queryKey: ["eventData"],
  });
