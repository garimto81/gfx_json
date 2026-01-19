"use client";

interface StatCardProps {
  title: string;
  value: number | string;
  variant?: "default" | "success" | "warning" | "error";
  icon?: string;
}

export function StatCard({
  title,
  value,
  variant = "default",
  icon,
}: StatCardProps) {
  const variantStyles = {
    default: "bg-white border-gray-200",
    success: "bg-green-50 border-green-200",
    warning: "bg-yellow-50 border-yellow-200",
    error: "bg-red-50 border-red-200",
  };

  const valueStyles = {
    default: "text-gray-900",
    success: "text-green-700",
    warning: "text-yellow-700",
    error: "text-red-700",
  };

  return (
    <div
      className={`rounded-lg border p-6 shadow-sm ${variantStyles[variant]}`}
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-gray-600">{title}</p>
        {icon && <span className="text-2xl">{icon}</span>}
      </div>
      <p className={`mt-2 text-3xl font-bold ${valueStyles[variant]}`}>
        {typeof value === "number" ? value.toLocaleString() : value}
      </p>
    </div>
  );
}
