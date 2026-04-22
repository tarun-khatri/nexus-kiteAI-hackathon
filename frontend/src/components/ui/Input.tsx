import { type InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export function Input({ label, className = "", id, ...props }: InputProps) {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");
  return (
    <div className="w-full">
      {label && (
        <label htmlFor={inputId} className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1.5">
          {label}
        </label>
      )}
      <input id={inputId} className={`input ${className}`} {...props} />
    </div>
  );
}
