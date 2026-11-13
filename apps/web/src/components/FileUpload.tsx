import React, { useState, useRef } from 'react';
import { cn } from '../lib/utils';
import { Icons } from './Icons';

export interface FileUploadProps {
  accept?: string;
  maxSizeBytes?: number;
  onFileSelect: (file: File) => void;
  isUploading?: boolean;
  uploadProgress?: number; // 0 - 100
  label?: string;
  error?: string;
}

export const FileUpload: React.FC<FileUploadProps> = ({
  accept = '.csv,text/csv',
  maxSizeBytes = 5 * 1024 * 1024, // 5MB default
  onFileSelect,
  isUploading = false,
  uploadProgress = 0,
  label = 'Upload CSV File',
  error,
}) => {
  const [isDragOver, setIsDragOver] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const validateAndSelect = (file: File) => {
    setValidationError(null);
    if (file.size > maxSizeBytes) {
      setValidationError(`File exceeds maximum size of ${Math.round(maxSizeBytes / (1024 * 1024))}MB.`);
      return;
    }
    setSelectedFile(file);
    onFileSelect(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndSelect(e.dataTransfer.files[0]);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      validateAndSelect(e.target.files[0]);
    }
  };

  const displayError = error || validationError;

  return (
    <div className="w-full flex flex-col gap-1.5 text-left">
      {label && <span className="text-[13px] font-medium text-text">{label}</span>}

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        onClick={() => !isUploading && inputRef.current?.click()}
        className={cn(
          'w-full border-2 border-dashed rounded-[10px] p-6 text-center transition-colors cursor-pointer select-none bg-surface',
          isDragOver ? 'border-primary bg-primary-subtle' : 'border-border hover:border-primary-border',
          isUploading && 'opacity-70 cursor-not-allowed',
          displayError ? 'border-danger' : ''
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          onChange={handleChange}
          disabled={isUploading}
          className="hidden"
        />

        <div className="flex flex-col items-center justify-center">
          <div className="w-10 h-10 rounded-full bg-bg border border-border flex items-center justify-center text-text-muted mb-2">
            <Icons.Calendar className="w-5 h-5 stroke-[1.5]" />
          </div>

          {selectedFile ? (
            <div>
              <p className="text-[14px] font-semibold text-text">{selectedFile.name}</p>
              <p className="text-[12px] text-text-muted mt-0.5">
                {(selectedFile.size / 1024).toFixed(1)} KB
              </p>
            </div>
          ) : (
            <div>
              <p className="text-[14px] font-medium text-text">
                <span className="text-primary font-semibold">Click to upload</span> or drag and drop
              </p>
              <p className="text-[12px] text-text-muted mt-0.5">CSV spreadsheet up to 5MB</p>
            </div>
          )}
        </div>

        {isUploading && (
          <div className="mt-4 w-full">
            <div className="w-full bg-border rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-primary h-full transition-all duration-200"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
            <span className="block text-[11px] text-text-secondary mt-1 tabular-nums">
              Uploading... {uploadProgress}%
            </span>
          </div>
        )}
      </div>

      {displayError && (
        <p className="text-[12px] text-danger" role="alert">
          {displayError}
        </p>
      )}
    </div>
  );
};

