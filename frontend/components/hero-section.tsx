// hero-section.tsx
"use client";
import { Button } from "@/components/ui/button";
import { Play } from "lucide-react";
import Link from "next/link";
import Image from "next/image";
import TrueFocus from "@/app/components/TrueFocus/TrueFocus";
import { cn } from "@/lib/utils";
import { FlipWords } from "./ui/flip-words";
import { motion } from "framer-motion";

export default function HeroSection() {
  return (
    <section className={" relative min-h-screen bg-[#F8F3EE] overflow-hidden"}>
      {/* Faded Background Text */}
      <div className="absolute top-36 inset-0 flex items-center justify-center pointer-events-none">
        <h1
          className={`text-[8rem] font-baskervville md:text-[12rem] lg:text-[19rem] font-light bg-gradient-to-b from-[#efe6d3] via-[#ede6d3] to-[#f2ebde] text-transparent bg-clip-text select-none whitespace-nowrap`}
        >
          <FlipWords
            className="text-[8rem] font-baskervville md:text-[12rem] lg:text-[19rem] font-light bg-gradient-to-b from-[#efe6d3] via-[#ede6d3] to-[#f2ebde] text-transparent bg-clip-text select-none whitespace-nowrap"
            words={["Auditor", "Analyst", "CFO"]}
          />
        </h1>
      </div>

      {/* Main Content Container */}
      <div className="container mx-auto px-4 pt-8 pb-2 relative h-screen flex flex-col">
        {/* Title */}
        <div className="text-center mb-2">
          <h1 className="text-[2.8rem] md:text-[3.8rem] lg:text-[5rem] font-light tracking-wider leading-tight text-[#2A2A2A]">
            {/* Focus on your startup’s growth – let AI handle the legal work. */}
            <TrueFocus
              sentence="Focus on the business, not the paperwork"
              manualMode={false}
              blurAmount={1.5}
              borderColor="black"
              animationDuration={0.9}
              pauseBetweenAnimations={0.7}
            />{" "}
            <span
              className={cn("italic text- text-black font-display")}
            >
              let Gemma handle compliance.
            </span>
          </h1>
        </div>

        {/* Main Content Area with Three Columns */}
        <div className="flex-grow flex items-center justify-center relative max-w-7xl mx-auto w-full">
          <div className="grid grid-cols-3 gap-8 items-center  w-full h-full">
            {/* Left Side - Text and Arrow */}
            <div className="flex flex-col justify-end mb-44 h-full">
              <div className="flex items-start flex-col space-x-4 mb-8">
                {/* Down Arrow */}
                <div className="flex flex-col justify-center w-[52%] items-center">
                  <div className="w-0.5 h-12 bg-[#2A2A2A] mb-2"></div>
                  <div className="w-0 h-0 border-l-[4px] border-r-[4px] border-t-[8px] border-l-transparent border-r-transparent border-t-[#2A2A2A]"></div>
                </div>

                {/* Text Content */}
                <div>
                  <p
                    className="text-base font-body md:text-lg font-light text-[#2A2A2A] leading-relaxed"
                  >
                    Transaction, Invoice & Onboarding-Document
                    <br />
                    Analysis, Powered by Gemma.
                  </p>
                </div>
              </div>

              {/* Gavel Image */}
              {/* <div className="w-30 absolute bottom-[17%] left-[14%] translate-x-[-20%] translate-y-[-15%] h-20 ">
                <Image
                  src="/images/gavel.png"
                  alt="Legal Gavel"
                  width={120}
                  height={80}
                  className="object-contain"
                />
              </div> */}
            </div>

            {/* Center - Statue Image */}
            <div className="flex justify-center  w-full items-center h-full">
              <div className="relative rounded-3xl p-8 w-full max-w-md">
                <motion.div
                  className="relative w-full h-[500px]"
                  animate={{
                    y: [0, -20, 0]
                  }}
                  transition={{
                    duration: 3,
                    repeat: Infinity,
                    ease: "easeInOut"
                  }}
                >
                  <Image
                    src="/images/lady-justice-statue.png"
                    alt="Lady Justice Statue"
                    fill
                    className="object-contain drop-shadow-2xl"
                    priority
                  />
                </motion.div>
              </div>
            </div>

            {/* Right Side - Text and Play Button */}
            <div className="flex flex-col justify-start mt-24 h-full">
              <div className="text-right mb-8">
                <p
                  className="text-sm md:text-base font-body font-light text-[#2A2A2A] max-w-[280px] leading-relaxed ml-auto"
                >
                  We analyse transactions, invoices, onboarding documents and
                  company policies in real time, flag anomalies against 40
                  compliance rules, and estimate penalty exposure before a
                  regulator does. Let GemmaFin OS run the triage.
                </p>
              </div>

              {/* Play Button with Decorative Elements */}
              <div className="flex justify-end">
                <div className="relative">
                  {/* Decorative dots around the button */}
                  <div className="absolute -top-3 -right-3">
                    <div className="flex space-x-1">
                      <div className="w-1 h-1 bg-[#2A2A2A] rounded-full"></div>
                      <div className="w-1 h-1 bg-[#2A2A2A] rounded-full"></div>
                      <div className="w-1 h-1 bg-[#2A2A2A] rounded-full"></div>
                    </div>
                    <div className="flex space-x-1 mt-1">
                      <div className="w-1 h-1 bg-[#2A2A2A] rounded-full"></div>
                      <div className="w-1 h-1 bg-[#2A2A2A] rounded-full"></div>
                      <div className="w-1 h-1 bg-[#2A2A2A] rounded-full"></div>
                    </div>
                    <div className="flex space-x-1 mt-1">
                      <div className="w-1 h-1 bg-[#2A2A2A] rounded-full"></div>
                      <div className="w-1 h-1 bg-[#2A2A2A] rounded-full"></div>
                      <div className="w-1 h-1 bg-[#2A2A2A] rounded-full"></div>
                    </div>
                  </div>
                  <Link
                    href="/sign-up"
                    aria-label="Get started with GemmaFin OS"
                    className="w-16 h-16 rounded-full border-2 border-[#2A2A2A] flex items-center justify-center hover:bg-[#2A2A2A] hover:text-[#F8F3EE] transition-colors group"
                  >
                    <Play className="w-5 h-5 fill-current translate-x-0.5" />
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Mobile Layout - Stack vertically on smaller screens */}
        <div className="lg:hidden flex-grow flex flex-col items-center justify-center space-y-8 pt-8">
          {/* Statue Image */}
          <div className="relative bg-[#E8DDD1] rounded-3xl p-6 w-full ">
            <motion.div
              className="relative w-full h-80"
              animate={{
                y: [0, -15, 0]
              }}
              transition={{
                duration: 3,
                repeat: Infinity,
                ease: "easeInOut"
              }}
            >
              <Image
                src="/images/lady-justice-statue.png"
                alt="Lady Justice Statue"
                fill
                className="object-none drop-shadow-2xl"
                priority
              />
            </motion.div>
          </div>

          {/* Bottom Content for Mobile */}
          <div className="flex  items-end justify-end w-full px-4">
            {/* Left Side Mobile */}
            <div className="flex items-end space-x-2">
              <div className="flex flex-col items-center">
                <div className="w-0.5 h-8 bg-[#2A2A2A] mb-2"></div>
                <div className="w-0 h-0 border-l-[4px] border-r-[4px] border-t-[8px] border-l-transparent border-r-transparent border-t-[#2A2A2A]"></div>
              </div>
              <div>
                <p
                  className="text-sm font-body font-light text-[#2A2A2A] leading-relaxed"
                >
                  Transaction, Invoice & Onboarding-Document
                  <br />
                  Analysis, Powered by Gemma.
                </p>
              </div>
            </div>

            {/* Right Side Mobile */}
            <div className="flex items-end h-full space-x-4">
              <div className="text-right">
                <p
                  className="text-xs font-body font-light text-[#2A2A2A] max-w-[200px] leading-relaxed"
                >
                  Real-time anomaly detection across transactions, invoices
                  and onboarding documents — with penalty exposure estimates
                  before a regulator finds the gap.
                </p>
              </div>
              <Link href="/sign-up" aria-label="Get started with GemmaFin OS" className="w-12 h-12 rounded-full border-2 border-[#2A2A2A] flex items-center justify-center">
                <Play className="w-4 h-4 fill-current translate-x-0.5" />
              </Link>
            </div>
          </div>

          {/* Gavel Image Mobile */}
          {/* <div className="self-start ml-8">
            <Image
              src="/images/gavel.png"
              alt="Legal Gavel"
              width={60}
              height={30}
              className="object-contain"
            />
          </div> */}
        </div>
      </div>
    </section>
  );
}
