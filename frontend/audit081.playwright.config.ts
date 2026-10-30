import {defineConfig} from '@playwright/test'
import base from './playwright.config'
export default defineConfig({...base,testDir:'./audit',testMatch:'**/v081.browser.probe.ts',projects:[{name:'chromium',use:{browserName:'chromium'}}]})
