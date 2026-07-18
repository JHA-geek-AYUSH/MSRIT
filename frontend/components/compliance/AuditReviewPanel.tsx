"use client";

import { useState, useEffect } from "react";
import { format } from "date-fns";

export default function AuditReviewPanel() {
  const [audits, setAudits] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState<string | null>(null);

  useEffect(() => {
    fetchAudits();
  }, []);

  const fetchAudits = async () => {
    try {
      const res = await fetch("http://localhost:8000/v1/compliance/audit");
      if (res.ok) {
        const data = await res.json();
        setAudits(data.audits || []);
      }
    } catch (err) {
      console.error("Failed to fetch audits", err);
    } finally {
      setLoading(false);
    }
  };

  const handleReview = async (auditId: string, status: string) => {
    setProcessing(auditId);
    try {
      const res = await fetch(`http://localhost:8000/v1/compliance/audit/${auditId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, comments: "Reviewed by Officer" }),
      });
      if (res.ok) {
        setAudits(audits.map(a => a.id === auditId ? { ...a, status } : a));
      }
    } catch (err) {
      console.error("Failed to review audit", err);
    } finally {
      setProcessing(null);
    }
  };

  if (loading) return <div className="text-white/50 p-8">Loading audit queue...</div>;

  return (
    <div className="space-y-6">
      {audits.map((audit) => (
        <div key={audit.id} className="bg-[#1C1C1C] border border-white/10 rounded-xl p-6">
          <div className="flex justify-between items-start mb-4">
            <div>
              <h3 className="text-xl font-semibold text-white">{audit.matter_title}</h3>
              <p className="text-white/50 text-sm mt-1">
                Generated {format(new Date(audit.created_at), "MMM d, yyyy h:mm a")}
              </p>
            </div>
            <div className={`px-3 py-1 rounded-full text-xs font-medium border
              ${audit.status === 'pending' ? 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20' : 
                audit.status === 'approved' ? 'bg-green-500/10 text-green-500 border-green-500/20' : 
                'bg-red-500/10 text-red-500 border-red-500/20'}`}>
              {audit.status.toUpperCase()}
            </div>
          </div>
          
          <div className="bg-[#121212] rounded-lg p-4 mb-6">
            <p className="text-white/70 text-sm font-medium mb-2">Original Query:</p>
            <p className="text-white font-mono text-sm">{audit.query_message}</p>
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <span className="text-white/50 text-sm">AI Suggested Tier:</span>
              <span className="bg-white/5 text-white px-3 py-1 rounded-md text-sm font-medium">
                {audit.original_tier.toUpperCase()}
              </span>
            </div>

            {audit.status === 'pending' && (
              <div className="flex space-x-3">
                <button
                  disabled={processing === audit.id}
                  onClick={() => handleReview(audit.id, 'rejected')}
                  className="px-4 py-2 rounded-lg bg-red-500/10 text-red-500 font-medium hover:bg-red-500/20 transition-colors"
                >
                  Reject
                </button>
                <button
                  disabled={processing === audit.id}
                  onClick={() => handleReview(audit.id, 'approved')}
                  className="px-4 py-2 rounded-lg bg-green-500/10 text-green-500 font-medium hover:bg-green-500/20 transition-colors"
                >
                  Approve
                </button>
              </div>
            )}
          </div>
        </div>
      ))}
      {audits.length === 0 && (
        <div className="text-center py-12 text-white/50">
          No audits pending review.
        </div>
      )}
    </div>
  );
}
