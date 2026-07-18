"use client";

import { Header } from "@/components/layout/Header";
import HeroSection from "@/components/hero-section";
import FeaturesSection from "@/components/features-section";
import HowItWorksSection from "@/components/how-it-works-section";
import StorySection from "@/components/story-section";
import Footer from "@/components/footer";

export default function Home() {
  return (
    <>
      <div className="min-h-screen bg-cream-50 overflow-x-clip">
        {/* Static Background - Always visible */}
        <div className="fixed inset-0 bg-cream-50 z-0"></div>

        {/* Main Content with Section-Specific Grains */}
        <div className="relative z-10">
          <Header />

          {/* Hero Section - Full Width Grain */}
          <div className="relative">
            <HeroSection />
          </div>

          {/* Features Section - Left Half Grain */}
          <div className="relative">
            <FeaturesSection />
          </div>

          {/* How It Works Section */}
          <div className="relative">
            <HowItWorksSection />
          </div>

          {/* Story Section */}
          <div className="relative">
            <StorySection />
          </div>

          {/* Footer */}
          <Footer />
        </div>

        {/* Sticky footer with correct branding */}
        <div className="w-full bg-[#efefef] items-center relative justify-center h-full overflow-auto">
          <div className="sticky z-0 bottom-0 left-0 w-full h-80 bg-white flex justify-center items-center">
            <div className="relative overflow-hidden w-full h-full flex justify-end px-12 text-right items-start py-12 text-[#ff5941]">
              <div className="flex flex-row space-x-12 sm:space-x-16 md:space-x-24 text-sm sm:text-lg md:text-xl">
                <div className="text-center space-y-2">
                  <p className="text-[#8B7355] text-sm">
                    Copyright 2025 Designed by Team AlphaQ
                  </p>
                  <p className="text-[#8B7355] text-sm">
                    Powered by Jazzee Technologies
                  </p>
                </div>
              </div>
              <h2 className="absolute bottom-0 left-0 translate-y-1/4 sm:text-[192px] text-[80px] text-brown-500 font-bold tracking-tighter">
                GemmaFin
              </h2>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
