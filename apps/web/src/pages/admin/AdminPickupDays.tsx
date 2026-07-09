import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import {
  AdminPickupDay,
  AdminPickupDayIn,
  AdminPickupDayUpdateIn,
  api,
} from "../../api/client";

type NewDayFields = {
  date: string;
  start_time: string;
  end_time: string;
  slot_minutes: number;
  slot_capacity: number;
};

function PickupDayRow({
  day,
  disabled,
  onToggle,
  onUpdateCapacity,
}: {
  day: AdminPickupDay;
  disabled: boolean;
  onToggle: (day: AdminPickupDay) => void;
  onUpdateCapacity: (id: string, capacity: number) => void;
}) {
  const [capacity, setCapacity] = useState(String(day.slot_capacity));

  return (
    <tr>
      <td>{day.date}</td>
      <td>{day.start_time}–{day.end_time}</td>
      <td>{day.slot_minutes} min</td>
      <td>
        <input
          aria-label={`${day.date} capacity`}
          type="number"
          min="1"
          value={capacity}
          onChange={(event) => setCapacity(event.target.value)}
        />
      </td>
      <td>{day.is_available ? "Available" : "Unavailable"}</td>
      <td>
        <button disabled={disabled} onClick={() => onUpdateCapacity(day.id, Number(capacity))}>
          Save
        </button>
        <button disabled={disabled} onClick={() => onToggle(day)}>
          {day.is_available ? "Disable" : "Enable"}
        </button>
      </td>
    </tr>
  );
}

export function AdminPickupDays({ csrfToken }: { csrfToken: string }) {
  const queryClient = useQueryClient();
  const days = useQuery({
    queryKey: ["admin", "pickup-days"],
    queryFn: () => api<AdminPickupDay[]>("/admin/pickup-days"),
  });

  const updateDay = useMutation({
    mutationFn: ({ id, body }: { id: string; body: AdminPickupDayUpdateIn }) =>
      api<AdminPickupDay>(`/admin/pickup-days/${id}`, {
        method: "PATCH",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify(body),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "pickup-days"] }),
  });

  const createDay = useMutation({
    mutationFn: (body: AdminPickupDayIn) =>
      api<AdminPickupDay>("/admin/pickup-days", {
        method: "POST",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "pickup-days"] });
      reset();
    },
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<NewDayFields>({
    defaultValues: { start_time: "16:00", end_time: "19:00", slot_minutes: 15, slot_capacity: 2 },
  });

  function submitNewDay(fields: NewDayFields) {
    createDay.mutate({
      date: fields.date,
      start_time: fields.start_time,
      end_time: fields.end_time,
      slot_minutes: Number(fields.slot_minutes),
      slot_capacity: Number(fields.slot_capacity),
    });
  }

  return (
    <div className="admin-pickup-days">
      {updateDay.isError && <p role="alert">{updateDay.error.message}</p>}
      {createDay.isError && <p role="alert">{createDay.error.message}</p>}
      {days.isLoading && <p role="status">Loading pickup days…</p>}
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Window</th>
            <th>Slot size</th>
            <th>Capacity</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {days.data?.map((day) => (
            <PickupDayRow
              key={day.id}
              day={day}
              disabled={updateDay.isPending}
              onToggle={(target) =>
                updateDay.mutate({ id: target.id, body: { is_available: !target.is_available } })
              }
              onUpdateCapacity={(id, capacity) => updateDay.mutate({ id, body: { slot_capacity: capacity } })}
            />
          ))}
        </tbody>
      </table>
      {days.data?.length === 0 && <p>No upcoming pickup days configured.</p>}

      <h2>Add a pickup day</h2>
      <form onSubmit={handleSubmit(submitNewDay)}>
        <label>
          Date
          <input type="date" {...register("date", { required: true })} />
        </label>
        {errors.date && <span role="alert">Date is required.</span>}
        <div className="field-pair">
          <label>
            Start time
            <input type="time" {...register("start_time", { required: true })} />
          </label>
          <label>
            End time
            <input type="time" {...register("end_time", { required: true })} />
          </label>
        </div>
        <div className="field-pair">
          <label>
            Slot minutes
            <input type="number" min="5" {...register("slot_minutes", { required: true, valueAsNumber: true })} />
          </label>
          <label>
            Slot capacity
            <input type="number" min="1" {...register("slot_capacity", { required: true, valueAsNumber: true })} />
          </label>
        </div>
        <button className="button" disabled={createDay.isPending}>
          {createDay.isPending ? "Creating…" : "Add pickup day"}
        </button>
      </form>
    </div>
  );
}
