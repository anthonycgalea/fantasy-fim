import { createLazyFileRoute } from "@tanstack/react-router";
import { useEventData } from "@/api/useEventData";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import React from "react";
import { EventData } from "@/types/EventData";

export const EventsPage = () => {
  const eventData = useEventData();
  const [sortConfig, setSortConfig] = React.useState<{
    key: keyof EventData;
    direction: "ascending" | "descending";
  }>({ key: "event_name", direction: "ascending" });

  const requestSort = (key: keyof EventData) => {
    setSortConfig((prev) => {
      let direction: "ascending" | "descending" = "ascending";
      if (prev.key === key && prev.direction === "ascending") {
        direction = "descending";
      }
      return { key, direction };
    });
  };

  const sortedData = React.useMemo(() => {
    if (!eventData.data) return [] as EventData[];
    const items = [...eventData.data];
    items.sort((a, b) => {
      const aVal = a[sortConfig.key] ?? 0;
      const bVal = b[sortConfig.key] ?? 0;
      if (aVal < bVal) return sortConfig.direction === "ascending" ? -1 : 1;
      if (aVal > bVal) return sortConfig.direction === "ascending" ? 1 : -1;
      return 0;
    });
    return items;
  }, [eventData.data, sortConfig]);

  const getArrow = (key: keyof EventData) => {
    if (sortConfig.key !== key) return null;
    return sortConfig.direction === "ascending" ? " \u25B2" : " \u25BC";
  };

  if (eventData.isLoading) {
    return (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Event Name</TableHead>
            <TableHead>Team Count</TableHead>
            <TableHead>Max EPA</TableHead>
            <TableHead>EPA 8</TableHead>
            <TableHead>EPA 24</TableHead>
            <TableHead>Average EPA</TableHead>
            <TableHead>Median EPA</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {Array(3)
            .fill(null)
            .map((_, i) => (
              <TableRow key={i}>
                {Array(7)
                  .fill(null)
                  .map((_, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full" />
                    </TableCell>
                  ))}
              </TableRow>
            ))}
        </TableBody>
      </Table>
    );
  }

  return (
    <div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead onClick={() => requestSort("event_name")}>Event Name{getArrow("event_name")}</TableHead>
            <TableHead onClick={() => requestSort("teamcount")}>Team Count{getArrow("teamcount")}</TableHead>
            <TableHead onClick={() => requestSort("maxepa")}>Max EPA{getArrow("maxepa")}</TableHead>
            <TableHead onClick={() => requestSort("top8epa")}>EPA 8{getArrow("top8epa")}</TableHead>
            <TableHead onClick={() => requestSort("top24epa")}>EPA 24{getArrow("top24epa")}</TableHead>
            <TableHead onClick={() => requestSort("avgepa")}>Average EPA{getArrow("avgepa")}</TableHead>
            <TableHead onClick={() => requestSort("medianepa")}>Median EPA{getArrow("medianepa")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sortedData.map((event, index) => (
            <TableRow key={index}>
              <TableCell>{event.event_name}</TableCell>
              <TableCell>{event.teamcount}</TableCell>
              <TableCell>{event.maxepa}</TableCell>
              <TableCell>{event.top8epa}</TableCell>
              <TableCell>{event.top24epa}</TableCell>
              <TableCell>{Math.round(event.avgepa ?? 0)}</TableCell>
              <TableCell>{event.medianepa}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
};

export const Route = createLazyFileRoute("/eventData")({
  component: EventsPage,
});
