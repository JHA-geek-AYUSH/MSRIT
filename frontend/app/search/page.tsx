"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Search, Loader2, FileText, ExternalLink } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { useToast } from "@/hooks/use-toast";
import { SearchFiltersComponent, SearchFilters } from "@/components/search/SearchFilters";
import { apiClient } from "@/lib/api";

interface SearchResult {
  id: string;
  title: string;
  description: string;
  type: "case" | "statute" | "document" | "precedent";
  date?: string;
  source?: string;
  relevance_score?: number;
  url?: string;
  excerpt?: string;
}

function SearchContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { toast } = useToast();

  const [searchTerm, setSearchTerm] = useState(searchParams.get("q") || "");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [totalResults, setTotalResults] = useState(0);
  const [searchTime, setSearchTime] = useState(0);
  const [hasSearched, setHasSearched] = useState(false);
  const [filters, setFilters] = useState<SearchFilters>({ limit: 20, offset: 0 });

  useEffect(() => {
    const initialQuery = searchParams.get("q");
    if (initialQuery) {
      setSearchTerm(initialQuery);
      performSearch(initialQuery, filters);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const performSearch = async (query: string, searchFilters: SearchFilters = filters) => {
    if (!query.trim()) {
      toast({ title: "Search term required", description: "Please enter a search term", variant: "destructive" });
      return;
    }

    setIsLoading(true);
    setHasSearched(true);

    const t0 = performance.now();
    try {
      const response = await apiClient.search(query, {
        type: searchFilters.type as any,
        date_from: searchFilters.date_from as string | undefined,
        date_to: searchFilters.date_to as string | undefined,
        limit: searchFilters.limit,
        offset: searchFilters.offset,
      });

      const took = Math.round(performance.now() - t0);
      setSearchTime(took);

      if (response.error) {
        toast({ title: "Search failed", description: response.error, variant: "destructive" });
        setResults([]);
        setTotalResults(0);
      } else if (response.data) {
        setResults(response.data.results ?? []);
        setTotalResults(response.data.total ?? 0);
      }

      // Update URL
      const params = new URLSearchParams();
      params.set("q", query);
      if (searchFilters.type) params.set("type", String(searchFilters.type));
      if (searchFilters.date_from) params.set("date_from", String(searchFilters.date_from));
      if (searchFilters.date_to) params.set("date_to", String(searchFilters.date_to));
      router.push(`/search?${params.toString()}`, { scroll: false });
    } catch (error) {
      setSearchTime(Math.round(performance.now() - t0));
      toast({ title: "Search failed", description: "An unexpected error occurred", variant: "destructive" });
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const sf = { ...filters, offset: 0 };
    setFilters(sf);
    performSearch(searchTerm, sf);
  };

  const ResultCard = ({ result }: { result: SearchResult }) => (
    <Card className="group hover:shadow-xl transition-all duration-200 border-black/10 bg-white">
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[11px] uppercase tracking-wider border border-black text-black px-2 py-0.5 rounded-full">
                {result.type}
              </span>
              {result.relevance_score !== undefined && (
                <span className="text-[11px] text-gray-600">
                  Relevance {(result.relevance_score * 100).toFixed(0)}%
                </span>
              )}
            </div>
            <h3 className="text-lg font-medium text-black group-hover:translate-x-[1px] transition-transform">
              {result.title}
            </h3>
            {(result.source || result.date) && (
              <div className="text-xs text-gray-600 mt-1">
                {[result.source, result.date].filter(Boolean).join(" • ")}
              </div>
            )}
            <p className="text-sm text-gray-800 mt-3">{result.description}</p>
            {result.excerpt && (
              <blockquote className="text-sm text-gray-700 italic border-l-2 border-gray-300 pl-3 mt-3">
                "{result.excerpt}"
              </blockquote>
            )}
          </div>
          {result.url && result.url !== "#" && (
            <Button
              variant="ghost"
              className="text-black hover:bg-black/5 shrink-0"
              onClick={() => window.open(result.url, "_blank")}
              aria-label="Open source"
            >
              <ExternalLink className="w-4 h-4" />
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );

  return (
    <div className="min-h-screen bg-[#EFEAE3]">
      <Header />
      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-black mb-2">GemmaFinOS Search</h1>
          <p className="text-gray-700">Search through cases, statutes, documents, and precedents</p>
        </div>

        {/* Search bar */}
        <form onSubmit={handleSearch} className="mb-6">
          <div className="relative max-w-3xl mx-auto">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Search className="h-5 w-5 text-gray-500" />
            </div>
            <Input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search for cases, statutes, precedents..."
              className="pl-10 pr-24 rounded-full py-3 text-lg border-black/20 focus:border-black bg-white text-black placeholder:text-gray-500"
            />
            <div className="absolute inset-y-0 right-0 flex items-center pr-0">
              <Button
                type="submit"
                disabled={isLoading}
                className="bg-black hover:bg-black/90 text-white rounded-full px-4"
              >
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              </Button>
            </div>
          </div>
        </form>

        {/* Filters */}
        {hasSearched && (
          <div className="max-w-3xl mx-auto mb-6">
            <SearchFiltersComponent
              filters={filters}
              onFiltersChange={setFilters}
              onApplyFilters={() => {
                const sf = { ...filters, offset: 0 };
                setFilters(sf);
                if (searchTerm.trim()) performSearch(searchTerm, sf);
              }}
            />
          </div>
        )}

        {/* Results */}
        {hasSearched && (
          <div>
            {!isLoading && (
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h2 className="text-xl font-medium text-black">Search Results</h2>
                  <p className="text-gray-700 text-sm">
                    {totalResults.toLocaleString()} results · {searchTime}ms
                  </p>
                </div>
              </div>
            )}

            {isLoading && (
              <div className="flex flex-col items-center justify-center py-16">
                <div className="relative">
                  <div className="h-12 w-12 rounded-full border-2 border-black animate-spin border-t-transparent" />
                </div>
                <div className="mt-4 text-sm text-gray-700">Searching GemmaFinOS Knowledge Graph…</div>
                <div className="grid gap-4 md:grid-cols-2 mt-8 w-full">
                  {[...Array(4)].map((_, i) => (
                    <Card key={i} className="p-4 border-black/10">
                      <div className="space-y-3 animate-pulse">
                        <div className="h-5 w-3/4 bg-black/10 rounded" />
                        <div className="h-3 w-1/2 bg-black/10 rounded" />
                        <div className="h-3 w-full bg-black/10 rounded" />
                      </div>
                    </Card>
                  ))}
                </div>
              </div>
            )}

            {!isLoading && results.length > 0 && (
              <div className="grid gap-4 md:grid-cols-1 lg:grid-cols-2">
                {results.map((r) => <ResultCard key={r.id} result={r} />)}
              </div>
            )}

            {!isLoading && results.length === 0 && (
              <Card className="border-black/10">
                <CardContent className="text-center py-12">
                  <FileText className="h-16 w-16 text-black/30 mx-auto mb-4" />
                  <h3 className="text-xl font-medium text-black mb-2">No results found</h3>
                  <p className="text-gray-700 mb-4">
                    The search database may be empty — upload and index documents to enable search, or try different keywords.
                  </p>
                  <Button variant="outline" onClick={() => { setResults([]); setHasSearched(false); setSearchTerm(""); }}>
                    Clear Search
                  </Button>
                </CardContent>
              </Card>
            )}
          </div>
        )}

        {/* Empty state */}
        {!hasSearched && (
          <div className="text-center py-20 text-gray-500">
            <Search className="h-16 w-16 mx-auto mb-4 opacity-30" />
            <p className="text-lg font-medium">Search the GemmaFinOS knowledge base</p>
            <p className="text-sm mt-2 opacity-70">Type a query above — cases, statutes, or legal topics</p>
          </div>
        )}
      </main>
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#EFEAE3] flex items-center justify-center"><Loader2 className="h-8 w-8 animate-spin" /></div>}>
      <SearchContent />
    </Suspense>
  );
}
